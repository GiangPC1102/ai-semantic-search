import io
import logging
import os
from datetime import datetime
from app.core.config import settings

CONSOLE_FORMAT = "[%(asctime)s] - [%(levelname)s] - [%(filename)s] - [%(funcName)s()] - [%(lineno)d] - %(message)s"


def get_logger(stringio_obj, write_file=False):
    logger = logging.getLogger("PFS_Recommender")
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter(CONSOLE_FORMAT)

    if write_file:
        time_str = datetime.strftime(datetime.now(), "%Y%m%d")
        logger_file = os.path.join(
            settings.BASE_DIR, "logging_files", f"Run_{time_str}.log"
        )
        if not os.path.isfile(logger_file):
            os.makedirs(os.path.split(logger_file)[0], exist_ok=True)
            os.system(f"touch {logger_file}")

        file_logger = logging.FileHandler(logger_file, mode="a")
        file_logger.setFormatter(formatter)
        logger.addHandler(file_logger)

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    logger.addHandler(console)

    stringio_logger = logging.StreamHandler(stringio_obj)
    stringio_logger.setFormatter(formatter)
    logger.addHandler(stringio_logger)

    return logger


stringio_obj = io.StringIO()
logger = get_logger(stringio_obj, write_file=True)