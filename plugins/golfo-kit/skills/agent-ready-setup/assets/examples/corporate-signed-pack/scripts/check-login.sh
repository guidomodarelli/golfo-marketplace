#!/bin/bash
# Runs once per checkout (install): tells the developer to log in, never asks for a password itself.
set -u
if command -v acme > /dev/null 2>&1 && acme auth status > /dev/null 2>&1; then
  echo "acme: logged in"
else
  echo "acme: not logged in; run acme auth login"
fi
