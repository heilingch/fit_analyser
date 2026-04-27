#!/bin/bash

# Get the directory where the script is located
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

# Source the virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Run the application
exec python main.py "$@"
