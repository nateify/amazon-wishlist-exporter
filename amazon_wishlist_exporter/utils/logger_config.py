import logging
import sys

log_format = "%(asctime)s | %(levelname)s | %(message)s"
stdout_handler = logging.StreamHandler(sys.stdout)
stdout_handler.setLevel(logging.DEBUG)
stdout_handler.addFilter(lambda record: record.levelno < logging.ERROR)

stderr_handler = logging.StreamHandler(sys.stderr)
stderr_handler.setLevel(logging.ERROR)

logging.basicConfig(
    level=logging.INFO, format=log_format, datefmt="%H:%M:%S", handlers=[stdout_handler, stderr_handler]
)

logger = logging.getLogger(__name__)
