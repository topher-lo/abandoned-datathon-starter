"""Run this script to register flows to be managed by the Prefect Backend.
"""

from configparser import ConfigParser
from server.pipeline import wrangle_na_pipeline
from server.pipeline import e2e_pipeline

# Get configs
config = ConfigParser()
config.read('pipeline.ini')

PROJECT_NAME = config.get('prefect', 'PROJECT_NAME')

# Register Flows
wrangle_na_pipeline.register(project_name=PROJECT_NAME)
e2e_pipeline.register(project_name=PROJECT_NAME)