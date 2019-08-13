"""
Controllers for process-related requests.

The controllers in this module leverage
:mod:`arxiv.submission.core.process.process_source`, which provides an
high-level API for orchestrating source processing for all supported source
types.
"""

import io
import re
from http import HTTPStatus as status
from typing import Tuple, Dict, Any, Optional


import bleach
from werkzeug import MultiDict
from werkzeug.exceptions import InternalServerError, BadRequest, NotFound, \
    MethodNotAllowed
from flask import url_for, Markup
from wtforms import SelectField, widgets, HiddenField, validators

from arxiv.base import logging, alerts
from arxiv.forms import csrf
from arxiv.users.domain import Session
from arxiv.integration.api import exceptions

from arxiv.submission import save, SaveError, Submission
from arxiv.submission.process import process_source
from arxiv.submission.domain.compilation import Compilation
from arxiv.submission.domain.event import ConfirmSourceProcessed
from arxiv.submission.domain.preview import Preview
from arxiv.submission.domain.submission import Compilation, SubmissionContent
from arxiv.submission.services import PreviewService, Compiler

from ..util import load_submission
from .util import validate_command, user_and_client_from_session

logger = logging.getLogger(__name__)

Response = Tuple[Dict[str, Any], int, Dict[str, Any]]  # pylint: disable=C0103


SUPPORT = Markup(
    'If you continue to experience problems, please contact'
    ' <a href="mailto:help@arxiv.org"> arXiv support</a>.'
)


def file_process(method: str, params: MultiDict, session: Session,
                 submission_id: int, token: str, **kwargs: Any) -> Response:
    """
    Process the file compilation project.

    Parameters
    ----------
    method : str
        ``GET`` or ``POST``
    session : :class:`Session`
        The authenticated session for the request.
    submission_id : int
        The identifier of the submission for which the upload is being made.
    token : str
        The original (encrypted) auth token on the request. Used to perform
        subrequests to the file management service.

    Returns
    -------
    dict
        Response data, to render in template.
    int
        HTTP status code. This should be ``200`` or ``303``, unless something
        goes wrong.
    dict
        Extra headers to add/update on the response. This should include
        the `Location` header for use in the 303 redirect response, if
        applicable.

    """
    if method == "GET":
        return compile_status(params, session, submission_id, token)
    elif method == "POST":
        if params.get('action') in ['previous', 'next', 'save_exit']:
            _check_status(params, session, submission_id, token)
            # User is not actually trying to process anything; let flow control
            # in the routes handle the response.
            return {}, status.SEE_OTHER, {}
        return start_compilation(params, session, submission_id, token)
    raise MethodNotAllowed('Unsupported request')


def _check_status(params: MultiDict, session: Session,  submission_id: int,
                  token: str, **kwargs: Any) -> None:
    """
    Check for cases in which the preview already exists.

    This will catch cases in which the submission is PDF-only, or otherwise
    requires no further compilation.
    """
    submitter, client = user_and_client_from_session(session)
    submission, _ = load_submission(submission_id)

    if not submission.is_source_processed:
        form = CompilationForm(params)  # Providing CSRF protection.
        if not form.validate():
            raise BadRequest('Invalid request; please try again.')

        command = ConfirmSourceProcessed(creator=submitter, client=client)
        try:
            submission, _ = save(command, submission_id=submission_id)
        except SaveError as e:
            alerts.flash_failure(Markup(
                'There was a problem carrying out your request. Please'
                f' try again. {SUPPORT}'
            ))
            logger.error('Error while saving command %s: %s',
                         command.event_id, e)
            raise InternalServerError('Could not save changes') from e


def compile_status(params: MultiDict, session: Session, submission_id: int,
                   token: str, **kwargs: Any) -> Response:
    """
    Returns the status of a compilation.

    Parameters
    ----------
    session : :class:`Session`
        The authenticated session for the request.
    submission_id : int
        The identifier of the submission for which the upload is being made.
    token : str
        The original (encrypted) auth token on the request. Used to perform
        subrequests to the file management service.

    Returns
    -------
    dict
        Response data, to render in template.
    int
        HTTP status code. This should be ``200`` or ``303``, unless something
        goes wrong.
    dict
        Extra headers to add/update on the response. This should include
        the `Location` header for use in the 303 redirect response, if
        applicable.

    """
    submitter, client = user_and_client_from_session(session)
    submission, _ = load_submission(submission_id)
    form = CompilationForm()
    response_data = {
        'submission_id': submission_id,
        'submission': submission,
        'form': form,
        'status': None,
    }
    # Determine whether the current state of the uploaded source content has
    # been compiled.
    result: Optional[process_source.CheckResult] = None
    try:
        result = process_source.check(submission, submitter, client, token)
    except process_source.NoProcessToCheck as e:
        pass
    except process_source.FailedToCheckStatus as e:
        logger.error('Failed to check status: %s', e)
        alerts.flash_failure(Markup(
            'There was a problem carrying out your request. Please try'
            f' again. {SUPPORT}'
        ))
    if result is not None:
        response_data['status'] = result.status
        response_data.update(**result.extra)
    return response_data, status.OK, {}


def start_compilation(params: MultiDict, session: Session, submission_id: int,
                      token: str, **kwargs: Any) -> Response:
    submitter, client = user_and_client_from_session(session)
    submission, submission_events = load_submission(submission_id)
    form = CompilationForm(params)
    response_data = {
        'submission_id': submission_id,
        'submission': submission,
        'form': form,
        'status': None,
    }

    if not form.validate():
        raise BadRequest(response_data)

    try:
        result = process_source.start(submission, submitter, client, token)
    except process_source.FailedToStart as e:
        alerts.flash_failure(f"We couldn't process your submission. {SUPPORT}",
                             title="Processing failed")
        logger.error('Error while requesting compilation for %s: %s',
                     submission_id, e)
        raise InternalServerError(response_data) from e

    response_data['status'] = result.status
    response_data.update(**result.extra)

    if result.status == process_source.FAILED:
        alerts.flash_failure(f"Processing failed")
    else:
        alerts.flash_success(
            "We are processing your submission. This may take a minute or two."
            " This page will refresh automatically every 5 seconds. You can "
            " also refresh this page manually to check the current status. ",
            title="Processing started"
        )
    redirect = url_for('ui.file_process', submission_id=submission_id)
    return response_data, status.SEE_OTHER, {'Location': redirect}


def file_preview(params, session: Session, submission_id: int, token: str,
                 **kwargs: Any) -> Tuple[io.BytesIO, int, Dict[str, str]]:
    """Serve the PDF preview for a submission."""
    submitter, client = user_and_client_from_session(session)
    submission, submission_events = load_submission(submission_id)
    p = PreviewService.current_session()
    stream, pdf_checksum = p.get(submission.source_content.identifier,
                                 submission.source_content.checksum,
                                 token)
    headers = {'Content-Type': 'application/pdf'}
    return stream, status.OK, headers


def compilation_log(params, session: Session, submission_id: int, token: str,
                    **kwargs: Any) -> Response:
    submitter, client = user_and_client_from_session(session)
    submission, submission_events = load_submission(submission_id)
    checksum = params.get('checksum', submission.source_content.checksum)
    try:
        log = Compiler.get_log(submission.source_content.identifier, checksum,
                               token)
        headers = {'Content-Type': log.content_type}
        return log.stream, status.OK, headers
    except exceptions.NotFound:
        raise NotFound("No log output produced")


def compile(params: MultiDict, session: Session, submission_id: int,
            token: str, **kwargs) -> Response:
    redirect = url_for('ui.file_process', submission_id=submission_id)
    return {}, status.SEE_OTHER, {'Location': redirect}


class CompilationForm(csrf.CSRFForm):
    """Generate form to process compilation."""

    PDFLATEX = 'pdflatex'
    COMPILERS = [
        (PDFLATEX, 'PDFLaTeX')
    ]

    compiler = SelectField('Compiler', choices=COMPILERS,
                           default=PDFLATEX)
