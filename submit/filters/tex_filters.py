"""Filters for highlighting autotex log files."""

import re
import html

TEX = 'tex'
LATEX = 'latex'
PDFLATEX = 'pdflatex'

ENABLE_TEX = r'(\~+\sRunning tex.*\s\~+)'
ENABLE_LATEX = r'(\~+\sRunning latex.*\s\~+)'
ENABLE_PDFLATEX = r'(\~+\sRunning pdflatex.*\s\~+)'

DISABLE_HTEX = r'(\~+\sRunning htex.*\s\~+)'
DISABLE_HLATEX = r'(\~+\sRunning hlatex.*\s\~+)'
DISABLE_HPDFLATEX = r'(\~+\sRunning hpdflatex.*\s\~+)'

RUN_ORDER = ['last', 'first', 'second', 'third', 'fourth']

def initialize_error_summary() -> str:
    """Initialize the error_summary string with desired markuop."""
    error_summary = '\nSummary of <span class="tex-fatal">Critical Errors:</span>\n\n<ul>\n'
    return error_summary

def finalize_error_summary(error_summary: str) -> str:
    error_summary = error_summary + "</ul>\n"
    return error_summary

def compilation_log_display(autotex_log: str, submission_id: int,
                            compilation_status: str) -> str:
    """
    Highlight interesting features in autotex log.

    Parameters
    ----------
    autotex_log : str
        Complete autotex log containing output from series of TeX runs.

    Returns
    -------
        Returns highlighted autotex log.

    """
    # Don't do anything when log not generated
    if re.search(r'No log available.', autotex_log):
        return autotex_log

    # Create summary information detailing runs and markup key.

    run_summary = ("If you are attempting to compile "
                   "with a specific engine (PDFLaTeX, LaTeX, \nTeX) please "
                   "carefully review the appropriate log below.\n\n"
                   )

    # Key to highlighting

    key_summary = ""
        #(
        # "Key: \n"
        # "\t<span class=\"tex-fatal\">Severe warnings/errors.</span>'\n"
        # "\t<span class=\"tex-danger\">Warnings deemed important</span>'\n"
        # "\t<span class=\"tex-warning\">General warnings/errors from packages.</span>'\n"

        # "\t<span class=\"tex-ignore\">Warnings/Errors deemed unimportant. "
        # "Example: undefined references in first TeX run.</span>'\n"
        # "\t<span class=\"tex-success\">Indicates positive event, does not guarantee overall success</span>\n"
        # "\t<span class=\"tex-info\">Informational markup</span>\n"

        # "\n"
        # "\tNote: Almost all marked up messages are generated by TeX \n\tengine "
        # "or packages. The help or suggested highlights below \n\tmay be add to assist submitter.\n\n"
        # "\t<span class=\"tex-help\">References to arXiv help pages or other documentation.</span>\n"
        # "\t<span class=\"tex-suggestion\">Recommended solution based on "
        # "previous experience.</span>\n"
        # "\n\n"
        # )

    run_summary = run_summary + (
        f"Summary of TeX runs:\n\n"
    )

    new_log = ''

    last_run_for_engine = {}

    # TODO : THIS LIKELY BECOMES ITS OWN ROUTINE

    # Lets figure out what we have in terms of TeX runs
    #
    # Pattern is 'Running (engine) for the (run number) time'
    #
    # ~~~~~~~~~~~ Running hpdflatex for the first time ~~~~~~~~
    # ~~~~~~~~~~~ Running latex for the first time ~~~~~~~~
    run_regex = re.compile(r'\~+\sRunning (.*) for the (.*) time\s\~+',
                           re.IGNORECASE | re.MULTILINE)

    hits = run_regex.findall(autotex_log)

    enable_markup = []
    disable_markup = []

    success_last_engine = ''
    success_last_run = ''

    for run in hits:
        (engine, run) = run

        run_summary = run_summary + f"\tRunning {engine} for {run} time." + '\n'

        # Keep track of finaly run in the event compilation succeeded
        success_last_engine = engine
        success_last_run = run

        last_run_for_engine[engine] = run

        # Now, when we see a normal TeX run, we will eliminate the hypertex run.
        # Since normal run and hypertex run a basically identical this eliminates
        # unnecessary cruft. When hypertex run succeed it will be displayed and
        # marked up appropriately.

        if engine == PDFLATEX:
            disable_markup.append(DISABLE_HPDFLATEX)
            enable_markup.append(ENABLE_PDFLATEX)
        if engine == LATEX:
            disable_markup.append(DISABLE_HLATEX)
            enable_markup.append(ENABLE_LATEX)
        if engine == TEX:
            disable_markup.append(DISABLE_HTEX)
            enable_markup.append(ENABLE_TEX)

    run_summary = run_summary + '\n'

    for e, r in last_run_for_engine.items():
        run_summary = run_summary + f"\tLast run for engine {e} is {r}\n"

    # Ignore lines that we know submitters are not interested in or that
    # contain little useful value

    skip_markup = []

    current_engine = ''
    current_run = ''

    last_run = False

    # Filters  [css class, regex, run spec]
    #
    # Parameters:
    #
    #   css class: class to use for highlighting matching text
    #
    #   regex: regular expression that sucks up everything you want to highlight
    #
    #   run spec: specifies when to start applying filter
    #           OR apply to last run.
    #
    #     Possible Values: first, second, third, fourth, last
    #
    #     Examples:
    #           'first' - starts applying filter on first run.
    #           'last' - applies filter to last run of each particular engine.
    #           'third' - applies filter starting on third run.
    #
    #           run spec of 'second' will apply filter on second, third, ...
    #           run spec of 'last' will apply ONLY on last run for each engine.
    #
    # Order: Filters are applied in order they appear in list.
    #
    #        If you desire different highlighting for the same string match
    #        you must make sure the least restrictive filter is after more
    #        restrictive filter.
    #
    # Apply: Only one filter will be applied to a line from the log.
    #
    filters = [

        # Examples (these highlight random text at beginning of autotex log)
        # ['suggestion', r':.*PATH.*', 'second'], # Note ORDER is critical here
        # ['help', r':.*PATH.*', 'first'], # otherwise this rule trumps all PATH rules
        # ['suggestion', r'Set working directory to.*', ''],
        # ['ignore', 'Setting unix time to current time.*', ''],
        # ['help','Using source archive.*',''],
        # ['info', r'Using directory .* for processing.', ''],
        # ['warning', r'Copied file .* into working directory.', ''],
        # ['danger', 'nostamp: will not stamp PostScript', ''],
        # ['danger', r'TeX/AutoTeX.pm', ''],
        # ['fatal', r'override', ''],

        # Help - use to highlight links to help pages (or external references)
        # ['help', 'http://arxiv.org/help/.*', ''],

        # Individual filters are ordered by priority, more important highlighting first.

        ['ignore', r"get arXiv to do 4 passes\: Label\(s\) may have changed", ''],

        # Abort [uses 'fatal' class for markup and then disables other markup.
        ['abort', r'Fatal fontspec error: "cannot-use-pdftex"', ''],
        ['abort', r'The fontspec package requires either XeTeX or LuaTeX.', ''],
        ['abort', r'{cannot-use-pdftex}', ''],

        # These should be abort level errors but we are not set up to support
        # multiple errors of this type at the moment.
        ['fatal', '\*\*\* AutoTeX ABORTING \*\*\*', ''],
        ['fatal', '.*AutoTeX returned error: missfont.log present.', ''],
        ['fatal', 'dvips: Font .* not found; characters will be left blank.', ''],
        ['fatal', '.*missfont.log present.', ''],

        # Fatal
        ['fatal', r'Fatal .* error', ''],
        ['fatal', 'fatal', ''],

        # Danger
        ['danger', r'file (.*) not found', ''],
        ['danger', 'failed', ''],
        ['danger', 'emergency stop', ''],
        ['danger', 'not allowed', ''],
        ['danger', 'does not exist', ''],

        # TODO: Built execution priority into regex filter specification to
        # TODO: avoid having to worry about order of filters in this list.
        # Must run before warning regexes run
        ['danger', 'Package rerunfilecheck Warning:.*', 'last'],
        ['danger', '.*\(rerunfilecheck\).*', 'last'],
        ['danger', 'rerun', 'last'],

        # Warnings
        ['warning', r'Citation.*undefined', 'last'],  # needs to be 'last'
        ['warning', r'Reference.*undefined', 'last'],  # needs to be 'last'
        ['warning', r'No .* file', ''],
        ['warning', 'warning', 'second'],
        ['warning', 'unsupported', ''],
        ['warning', 'unable', ''],
        ['warning', 'ignore', ''],
        ['warning', 'undefined', 'second'],

        # Informational
        ['info', r'\~+\sRunning.*\s\~+', ''],
        ['info', r'(\*\*\* Using TeX Live 2016 \*\*\*)', ''],

        # Success
        ['success', r'(Extracting files from archive:)', ''],
        ['success', r'Successfully created PDF file:', ''],
        ['success', r'\*\* AutoTeX job completed. \*\*', ''],

        # Ignore
        # needs to be after 'warning' above that highlight same text
        ['ignore', r'Reference.*undefined', 'first'],
        ['ignore', r'Citation.*undefined', 'first'],
        ['ignore', 'warning', 'first'],
        ['ignore', 'undefined', 'first'],
    ]

    # Try to create summary containing errors deemed important for user
    # to address.
    error_summary = ''

    # Keep track of any errors we've already added to error_summary
    abort_markup = False
    xetex_luatex_abort = False
    emergency_stop = False
    missing_file = False
    missing_font_markup = False
    rerun_markup = False

    # Collect some state about

    final_run_had_errors = False
    final_run_had_warnings = False

    line_by_line = autotex_log.splitlines()

    # Enable markup. Program will turn off markup for extraneous run.
    markup_enabled = True

    for line in line_by_line:

        # Escape any HTML contained in the log
        line = html.escape(line)

        # Disable markup for TeX runs we do not want to mark up
        for regex in disable_markup:

            if re.search(regex, line, re.IGNORECASE):
                markup_enabled = False
                # new_log = new_log + f"DISABLE MARKUP:{line}\n"
                break

        # Enable markiup for runs that user is interested in
        for regex in enable_markup:

            if re.search(regex, line, re.IGNORECASE):
                markup_enabled = True
                # new_log = new_log + f"ENABLE MARKUP:{line}\n"
                # key_summary = key_summary + "\tRun: " + re.search(regex, line, re.IGNORECASE).group() + '\n'
                found = run_regex.search(line)
                if found:
                    current_engine = found.group(1)
                    current_run = found.group(2)
                    # new_log = new_log + f"Set engine:{current_engine} Run:{current_run}\n"

                if current_engine and current_run:
                    if last_run_for_engine[current_engine] == current_run:
                        # new_log = new_log + f"LAST RUN:{current_engine} Run:{current_run}\n"
                        last_run = True
                break

        # In the event we are not disabling/enabling markup
        if re.search(run_regex, line):
            found = run_regex.search(line)
            if found:
                current_engine = found.group(1)
                current_run = found.group(2)
                if last_run_for_engine[current_engine] == current_run:
                    # new_log = new_log + f"LAST RUN:{current_engine} Run:{current_run}\n"
                    last_run = True

        # Disable markup for TeX runs that we are not interested in.
        if not markup_enabled:
            continue

        # We are not done with this line until there is a match
        done_with_line = False

        for regex in skip_markup:
            if re.search(regex, line, re.IGNORECASE):
                done_with_line = True
                new_log = new_log + f"Skip line {line}\n"
                break

        if done_with_line:
            continue

        # Ignore, Info, Help, Warning, Danger, Fatal
        for level, filter, run in filters:
            regex = r'(' + filter + r')'

            # when we encounter fatal error limit highlighting to fatal
            # messages
            if abort_markup and level not in ['fatal', 'abort']:
                continue

            if not run:
                run = 'first'

                # if last_run and run and current_run and re.search('Package rerunfilecheck Warning', line):
                # if re.search('Package rerunfilecheck Warning', line):
                #new_log = new_log + (
                #        f"Settings: RUN:{run}:{RUN_ORDER.index(run)} "
                #        f" CURRENT:{current_run}:{RUN_ORDER.index(current_run)}:"
                #        f"Last:{last_run_for_engine[current_engine]} Filter:{filter}" + '\n')

            if run and current_run \
                    and ((RUN_ORDER.index(run) > RUN_ORDER.index(current_run)
                          or (run == 'last' and current_run != last_run_for_engine[current_engine]))):
                # if re.search('Package rerunfilecheck Warning', line):
                #    new_log = new_log + f"NOT RIGHT RUN LEVEL: SKIP:{filter}" + '\n'
                continue

            actual_level = level
            if level == 'abort':
                level = 'fatal'

            if re.search(regex, line, re.IGNORECASE):
                line = re.sub(regex, rf'<span class="tex-{level}">\1</span>',
                              line, flags=re.IGNORECASE)

                # Try to determine if there are problems with a successful compiliation
                if compilation_status == 'succeeded' \
                        and current_engine == success_last_engine \
                        and current_run == success_last_run:

                    if level == 'warning':
                        final_run_had_warnings = True
                    if level == 'danger' or level == 'fatal':
                        final_run_had_errors = True

                # Currently XeTeX/LuaTeX are the only full abort case.
                if not abort_markup and actual_level == 'abort' \
                        and (re.search('Fatal fontspec error: "cannot-use-pdftex"', line)
                             or re.search("The fontspec package requires either XeTeX or LuaTeX.", line)
                             or re.search("{cannot-use-pdftex}", line)):

                    if error_summary == '':
                        error_summary = initialize_error_summary()
                    else:
                        error_summary = error_summary + '\n'

                    error_summary = error_summary + (
                        "\t<li>At the current time arXiv does not support XeTeX/LuaTeX.\n\n"
                        '\tIf you believe that your submission requires a compilation '
                        'method \n\tunsupported by arXiv, please contact '
                        '<span class=\"tex-help\">help@arxiv.org</span> for '
                        '\n\tmore information and provide us with this '
                        f'submit/{submission_id} identifier.</li>')

                    xetex_luatex_abort = True
                    abort_markup = True

                # Hack alert - Cringe - Handle missfont while I'm working on converter.
                # TODO: Need to formalize detecting errors that need to be
                # TODO: reported in error summary
                if not missing_font_markup and level == 'fatal' \
                        and re.search("missfont.log present", line):

                    if error_summary == '':
                        error_summary = initialize_error_summary()
                    else:
                        error_summary = error_summary + '\n'

                    error_summary = error_summary + (
                        "\t<li>A font required by your paper is not available. "
                        "You may try to \n\tinclude a non-standard font or "
                        "substitue an alternative font. \n\tSee <span "
                        "class=\"tex-help\"><a href=\"https://arxiv.org/"
                        "help/00README#fontmap\">Custom Fontmaps</a></span>. If "
                        "this is due to a problem with \n\tour system, please "
                        "contact <span class=\"tex-help\">help@arxiv.org</span>"
                        " with details \n\tand provide us with this "
                        f'submission identifier: submit/{submission_id}.'
                        '</li>')

                    missing_font_markup = True

                # Hack alert - detect common problem where we need another TeX run
                if not rerun_markup and level == 'danger' \
                        and re.search("rerunfilecheck|rerun", line) \
                        and not re.search(r"get arXiv to do 4 passes\: Label\(s\) may have changed", line) \
                        and not re.search(r"oberdiek", line):

                    if error_summary == '':
                        error_summary = initialize_error_summary()
                    else:
                        error_summary = error_summary + '\n'

                    error_summary = error_summary + (
                        "\t<li>Analysis of the compilation log indicates "
                        "your submission \n\tmay need an additional TeX run. "
                        "Please add the following line \n\tto your source in "
                        "order to force an additional TeX run:\n\n"
                        "\t<span class=\"tex-help\">\\typeout{get arXiv "
                        "to do 4 passes: Label(s) may have changed. Rerun}</span>"
                        "\n\n\tAdd the above line just before <span "
                        "class=\"tex-help\">\end{document}</span> directive."
                        "/li>")

                    # Significant enough that we should turn on warning
                    final_run_had_warnings = True

                    # Only do this once
                    rerun_markup = True

                # Missing file needs to be kicked up in visibility and displayed in
                # compilation summary.
                #
                # There is an issue with the AutoTeX log where parts of the log
                # may be getting truncated. Therefore, for this error, we will
                # report the error if it occurs during any run.
                #
                # We might want to refine the activiation criteria for this
                # warning once the issue is resolved with truncated log.
                if not missing_file and level == 'danger' \
                        and re.search('file (.*) not found', line, re.IGNORECASE):

                    if error_summary == '':
                        error_summary = initialize_error_summary()
                    else:
                        error_summary = error_summary + '\n'

                    error_summary = error_summary + (
                        "<li>\tA file required by your submission was not found."
                        f"\n\t{line}\n\tPlease upload any missing files, or "
                        "correct any file naming issues, and then reprocess"
                        " your submission.</li>")

                    # Don't activate this so we can see bug I created above...
                    missing_file = True

                # Emergency stop tends to hand-in-hand with the file not found error.
                # If we havve already reported on the file not found error then
                # we won't add yet another warning about emergency stop.
                if not missing_file and not emergency_stop and level == 'danger' \
                        and re.search('emergency stop', line, re.IGNORECASE):

                    if error_summary == '':
                        error_summary = initialize_error_summary()
                    else:
                        error_summary = error_summary + '\n'

                    error_summary = error_summary + (
                        "\t<li>We detected an emergency stop during one of the TeX"
                        " compilation runs. Please review the compilation log"
                        " to determie whether there is a serious issue with "
                        "your submission source.</li>")

                    emergency_stop = True

                # We found a match so we are finished with this line
                break

        # Append line to new marked up log
        new_log = new_log + line + '\n'

    if error_summary:
        error_summary = finalize_error_summary(error_summary)

    # Now that we are done highlighting the autotex log we are able to roughly
    # determine/refine the status of a successful compilation.
    # Note that all submissions in 'Failed' status have warnings/errors we are not
    # sure about. When status is 'Succeeded' we are only concerned with warnings in
    # last run.
    status_class = 'success'
    if compilation_status == 'failed':
        status_class = 'fatal'
        if xetex_luatex_abort:
            display_status = "Failed: XeTeX/LuaTeX are not supported at current time."
        else:
            display_status = "Failed"
    elif compilation_status == 'succeeded':
        if final_run_had_errors and not final_run_had_warnings:
            display_status = ("Succeeded with possible errors. "
                              "\n\t\tBe sure to carefully inspect log (see below).")
            status_class = 'danger'
        elif not final_run_had_errors and final_run_had_warnings:
            display_status = ("Succeeded with warnings. We recommend that you "
                              "\n\t\tinspect the log (see below).")
            status_class = 'warning'
        elif final_run_had_errors and final_run_had_warnings:
            display_status = ("Succeeded with (possibly significant) errors and "
                              "warnings. \n\t\tPlease be sure to carefully inspect "
                              "log (see below).")
            status_class = 'danger'
        else:
            display_status = f"Succeeded!"
            status_class = 'success'
    else:
        status_class = 'warning'
        display_status = "Succeeded with warnings"

    status_line = f"\nProcessing Status: <span class=\"tex-{status_class}\">{display_status}</span>\n\n"

    # Put together a nice report, list TeX runs, markup info, and marked up log.
    # In future we can add 'Recommendation' section or collect critical errors.
    new_log = run_summary + status_line + error_summary + key_summary \
              + '\n\n<b>Marked Up Log:</b>\n\n' + new_log

    return new_log
