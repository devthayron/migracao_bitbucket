import logging
import os
from pathlib import Path


class FormatterColorido(logging.Formatter):
    CORES = {
        logging.DEBUG: "\033[36m",
        logging.INFO: "\033[37m",
        logging.WARNING: "\033[33m",
        logging.ERROR: "\033[31m",
        logging.CRITICAL: "\033[1;31m",
    }

    RESET = "\033[0m"

    def format(self, record):
        cor = self.CORES.get(record.levelno, "")
        mensagem = super().format(record)

        return f"{cor}{mensagem}{self.RESET}"


def setup_logging():
    Path("logs").mkdir(exist_ok=True)

    level = getattr(
        logging,
        os.getenv("LOG_LEVEL", "INFO").upper(),
        logging.INFO,
    )

    formato = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%d/%m/%Y %H:%M:%S",
    )

    console = logging.StreamHandler()
    console.setFormatter(
        FormatterColorido(
            "%(asctime)s | %(levelname)-8s | %(message)s",
            datefmt="%H:%M:%S",
        )
    )

    arquivo = logging.FileHandler(
        "logs/app.log",
        encoding="utf-8",
    )
    arquivo.setFormatter(formato)

    logging.basicConfig(
        level=level,
        handlers=[console, arquivo],
        force=True,
    )
