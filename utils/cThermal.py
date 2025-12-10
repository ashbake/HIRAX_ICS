from datetime import datetime
import logging, os
from pathlib import Path
import numpy as np
from astropy.io import fits


from cLogging import setup_logging
import logging, yaml

os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'

config_file = str(Path.cwd().resolve().parent / "config" / "guider.yaml")


class cThermal:
    def __init__(self, night, source, config_file=config_file):
        # Define attributes
        # read from config file, loads default config_file
        with open(config_file, 'r') as f:
            self.config = yaml.safe_load(f)

        self.source    = source # feed it a source string for the header
        self.night     = night # YYYYMMDD
        self.name      = self.config['name'] # should be H4Rpro
        self.file_format  = self.config['file_format']

        # make data and log dirs have sub direction of night string
        self.data_dir = Path(self.config['data_dir']) / self.night / self.name
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.log_dir = Path(self.config['log_dir']) / self.night
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # initiate logger
        self.logger = setup_logging(log_dir=self.log_dir,
                                    log_name=self.name,
                                    log_level=logging.DEBUG)
        

    def connect(self):
        # Retrieve singleton reference to system object
        pass