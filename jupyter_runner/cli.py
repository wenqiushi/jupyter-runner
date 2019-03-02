"""
Usage: jupyter-runner [options] <notebook>...

    --parameter-file=<PARAMETER_FILE>  Optional parameters files containing
    one parameter instance by line, setting the environment.
    Example with 2 sets of 3 parameters:
        VAR1=VAL1 VAR2=VAL2 VAR3=VAL3
        VAR1=VAL5 VAR2=VAL18 VAR3=VAL42
    --workers=<workers>  Maximum number of parallel execution  [Default: 1]
    --output-directory=<OUTPUT_DIRECTORY>  Output directory  [Default: .]
    --overwrite  Overwrite output files if they already exist.
    --format=<FORMAT>  Output format: html, notebook, script, asciidoc,
                       markdown, rst, pdf, html, latex, slides
                      [Default: html]
    --timeout=<TIMEOUT>  Cell execution timeout in seconds.  [Default: -1]
    --allow-errors  Allow errors during notebook execution.
    --debug  Enable debug logs
    --help  Display this help
    --version  Display version
"""
import logging
import multiprocessing
from inspect import signature
from shutil import which

from docopt import docopt

from . import __version__
from .execute import (
    get_tasks,
    execute_notebook,
)
from .constant import MAP_OUTPUT_EXTENSION
from .file_handler import (
    path_is_readable_file,
    create_writable_directory,
    disable_s3_verbose_logging,
)


LOG_FORMAT = '[%(asctime)s %(levelname)s] %(message)s'
LOGGER = logging.getLogger(__file__)


def log_input_options(args):
    LOGGER.debug('Running notebook(s) with following arguments:')
    for key in sorted(args.keys()):
        if key in ['--help', '--version']:
            continue
        LOGGER.debug('%s: %s', key, args[key])


def parse_args(args):
    """Return sanitize dict of arguments."""
    workers = int(args['--workers'])
    assert workers >= 1

    parameter_file = args['--parameter-file']
    assert parameter_file is None or path_is_readable_file(parameter_file), \
        '%s is not a readable parameter file' % parameter_file

    notebooks = args['<notebook>']
    for notebook in notebooks:
        assert path_is_readable_file(notebook), \
            '%s is not a readable notebook file' % notebook

    output_dir = args['--output-directory']
    create_writable_directory(output_dir)

    overwrite = args['--overwrite']

    output_format = args['--format']
    assert output_format in MAP_OUTPUT_EXTENSION.keys()

    if output_format == 'pdf':
        # Ensure necessary tool is installed
        assert which('xelatex') is not None, \
            'xelatex not found in PATH, necessary for PDF conversion.'

    timeout = args['--timeout']
    assert float(timeout), '--timeout should be a float.'

    allow_errors = args['--allow-errors']

    return dict(
        parameter_file=parameter_file,
        notebooks=notebooks,
        output_dir=output_dir,
        debug=args['--debug'],
        overwrite=overwrite,
        output_format=output_format,
        timeout=timeout,
        allow_errors=allow_errors,
        workers=workers,
    )


def main():
    """Main function of jupyter-run."""
    args = docopt(__doc__, version=__version__)

    # Determine log level
    debug = args['--debug']
    log_level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(level=log_level, format=LOG_FORMAT)
    disable_s3_verbose_logging()

    # In debug mode, log input options
    log_input_options(args)

    # Read and return sanitized arguments
    args = parse_args(args)

    # Retrieve individual task to run (product of parameters and notebooks)
    kw_tasks = get_tasks(
        parameter_file=args['parameter_file'],
        notebooks=args['notebooks'],
        output_dir=args['output_dir'],
        debug=args['debug'],
        overwrite=args['overwrite'],
        output_format=args['output_format'],
        timeout=args['timeout'],
        allow_errors=args['allow_errors'],
    )

    # Flatten list of kwargs to list of args
    tasks = [
        [kw_task[arg] for arg in signature(execute_notebook).parameters]
        for kw_task in kw_tasks
    ]

    ret_codes = []
    if args['workers'] > 1:
        with multiprocessing.Pool(args['workers']) as pool:
            ret_codes = pool.starmap(execute_notebook, tasks, chunksize=1)
    else:
        # Execute without multiprocessing to ease debugging
        for task in tasks:
            ret_codes.append(execute_notebook(*task))

    return max(ret_codes) if ret_codes else 0
