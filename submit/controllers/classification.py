"""
Controller for classification actions.

Creates an event of type `core.events.event.SetPrimaryClassification`
Creates an event of type `core.events.event.AddSecondaryClassification`
"""
from typing import Tuple, Dict, Any, List, Optional
from werkzeug import MultiDict
from werkzeug.exceptions import InternalServerError, BadRequest
from flask import url_for, Markup
from wtforms import SelectField, widgets, HiddenField, validators

from arxiv import status, taxonomy
from arxiv.forms import csrf
from arxiv.base import logging, alerts
from arxiv.submission.domain import Submission
from arxiv.submission import save
from arxiv.submission.exceptions import InvalidEvent, SaveError
from arxiv.users.domain import Session
from arxiv.submission import RemoveSecondaryClassification, \
    AddSecondaryClassification, SetPrimaryClassification

from .util import validate_command, OptGroupSelectField, \
    user_and_client_from_session
from ..util import load_submission

logger = logging.getLogger(__name__)  # pylint: disable=C0103

Response = Tuple[Dict[str, Any], int, Dict[str, Any]]  # pylint: disable=C0103


class ClassificationForm(csrf.CSRFForm):
    """Form for classification selection."""

    CATEGORIES = [
        (archive['name'], [
            (category_id, f"{category['name']} ({category_id})")
            for category_id, category in taxonomy.CATEGORIES_ACTIVE.items()
            if category['in_archive'] == archive_id
        ])
        for archive_id, archive in taxonomy.ARCHIVES_ACTIVE.items()
    ]
    """Categories grouped by archive."""

    ADD = 'add'
    REMOVE = 'remove'
    OPERATIONS = [
        (ADD, 'Add'),
        (REMOVE, 'Remove')
    ]
    operation = HiddenField(default=ADD, validators=[validators.optional()])
    category = OptGroupSelectField('Category', choices=CATEGORIES, default='')

    def filter_choices(self, submission: Submission, session: Session) -> None:
        """Remove redundant choices, and limit to endorsed categories."""
        selected = self.category.data
        primary = submission.primary_classification

        choices = [
            (archive, [
                (category, display) for category, display in archive_choices
                if session.authorizations.endorsed_for(category)
                and (((primary is None or category != primary.category)
                      and category not in submission.secondary_categories)
                     or category == selected)
            ])
            for archive, archive_choices in self.category.choices
        ]
        self.category.choices = [
            (archive, _choices) for archive, _choices in choices
            if len(_choices) > 0
        ]

    @classmethod
    def formset(cls, submission: Submission) \
            -> Dict[str, 'ClassificationForm']:
        """Generate a set of forms used to remove cross-list categories."""
        formset = {}
        if hasattr(submission, 'secondary_classification') and \
                submission.secondary_classification:
            for secondary in submission.secondary_classification:
                this_category = str(secondary.category)
                subform = cls(operation=cls.REMOVE, category=this_category)
                subform.category.widget = widgets.HiddenInput()
                formset[secondary.category] = subform
        return formset


class PrimaryClassificationForm(ClassificationForm):
    """Form for setting the primary classification."""

    def validate_operation(self, field) -> None:
        """Make sure the client isn't monkeying with the operation."""
        if field.data != self.ADD:
            raise validators.ValidationError('Invalid operation')


def classification(method: str, params: MultiDict, session: Session,
                   submission_id: int, **kwargs) -> Response:
    """Handle primary classification requests."""
    submitter, client = user_and_client_from_session(session)
    submission, submission_events = load_submission(submission_id)

    if method == 'GET':
        # Prepopulate the form based on the state of the submission.
        if submission.primary_classification \
                and submission.primary_classification.category:
            params['category'] = submission.primary_classification.category

        # Use the user's default category as the default for the form.
        params.setdefault('category', session.user.profile.default_category)

    params['operation'] = PrimaryClassificationForm.ADD

    form = PrimaryClassificationForm(params)
    form.filter_choices(submission, session)

    response_data = {
        'submission_id': submission_id,
        'submission': submission,
        'submitter': submitter,
        'client': client,
        'form': form
    }

    if method == 'POST':
        if not form.validate():
            raise BadRequest(response_data)

        command = SetPrimaryClassification(category=form.category.data,
                                           creator=submitter, client=client)
        if not validate_command(form, command, submission, 'category'):
            raise BadRequest(response_data)

        try:
            submission, _ = save(command, submission_id=submission_id)
            response_data['submission'] = submission
        except SaveError as e:
            logger.error('Could not save command: %s', e)
            raise InternalServerError(response_data) from e

        if params.get('action') in ['previous', 'save_exit', 'next']:
            return response_data, status.HTTP_303_SEE_OTHER, {}
    return response_data, status.HTTP_200_OK, {}


def cross_list(method: str, params: MultiDict, session: Session,
               submission_id: int, **kwargs) -> Response:

    submitter, client = user_and_client_from_session(session)
    submission, submission_events = load_submission(submission_id)

    form = ClassificationForm(params)
    form.operation._value = lambda: form.operation.data
    form.filter_choices(submission, session)

    # Create a formset to render removal option.
    #
    # We need forms for existing secondaries, to generate removal requests.
    # When the forms in the formset are submitted, they are handled as the
    # primary form in the POST request to this controller.
    formset = ClassificationForm.formset(submission)
    _primary_category = submission.primary_classification.category
    _primary = taxonomy.CATEGORIES[_primary_category]

    response_data = {
        'submission_id': submission_id,
        'submission': submission,
        'submitter': submitter,
        'client': client,
        'form': form,
        'formset': formset,
        'primary': {
            'id': submission.primary_classification.category,
            'name': _primary['name']
        },
    }

    if method == 'POST':
        # Make sure that the user is not attempting to move to a different
        # step.
        #
        # Since the interface provides an "add" button to add cross-list
        # categories, we only want to handle the form data if the user is not
        # attempting to move to a different step.
        action = params.get('action')
        if not action:
            if not form.validate():
                raise BadRequest(response_data)

            if form.operation.data == form.REMOVE:
                command_type = RemoveSecondaryClassification
            else:
                command_type = AddSecondaryClassification
            command = command_type(category=form.category.data,
                                   creator=submitter, client=client)
            if not validate_command(form, command, submission, 'category'):
                raise BadRequest(response_data)

            try:
                submission, _ = save(command, submission_id=submission_id)
                response_data['submission'] = submission
            except SaveError as e:
                raise InternalServerError(response_data) from e

            # Re-build the formset to reflect changes that we just made, and
            # generate a fresh form for adding another secondary. The POSTed
            # data should now be reflected in the formset.
            response_data['formset'] = ClassificationForm.formset(submission)
            form = ClassificationForm()
            form.operation._value = lambda: form.operation.data
            form.filter_choices(submission, session)
            response_data['form'] = form

            # Warn the user if they have too many secondaries.
            if len(submission.secondary_categories) > 3:
                alerts.flash_warning(Markup(
                    'Adding more than three cross-list classifications will'
                    ' result in a delay in the acceptance of your submission.'
                ))

        if action in ['previous', 'save_exit', 'next']:
            return response_data, status.HTTP_303_SEE_OTHER, {}
    return response_data, status.HTTP_200_OK, {}
