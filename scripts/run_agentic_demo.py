#!/usr/bin/env python3
import argparse
from zhijia_guardian.cli import demo

if __name__ == "__main__":
  parser = argparse.ArgumentParser()
  parser.add_argument("--config", default="configs/demo.yaml")
  raise SystemExit(demo(parser.parse_args().config))
