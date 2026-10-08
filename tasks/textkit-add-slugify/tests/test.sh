#!/bin/bash
# Two rewards: "correct" (hidden functional tests) and "adherence" (share of house
# conventions followed). Harbor reads /logs/verifier/reward.json.
cd /app
python -m pytest /tests/test_outputs.py -rA -p no:cacheprovider --junitxml=/logs/verifier/junit.xml
python /tests/score.py /logs/verifier/junit.xml > /logs/verifier/reward.json
cat /logs/verifier/reward.json
