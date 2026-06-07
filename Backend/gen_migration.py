import sys
import os
import argparse
from alembic.config import Config
from alembic import command

def main():
    alembic_cfg = Config("alembic.ini")
    command.revision(alembic_cfg, autogenerate=True, message="Add alerting tables")

if __name__ == "__main__":
    main()
