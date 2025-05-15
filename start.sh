#!/bin/bash

apt-get update && apt-get install -y ca-certificates

gunicorn app:app --bind 0.0.0.0:$PORT
