#!/bin/bash
source activate ember
set -e
set -f
# Our dataset
data_dir="" # directory to ember_if.json

max_token=10
eval_only='false'
eval_model='Meta-Llama-3-70B-Instruct' # gpt-4-mini, gpt35, gpt-4-turbo, gpt-4o, Meta-Llama-3-70B-Instruct, Meta-Llama-3-8B-Instruct

python run_ifeval.py --data_dir ${data_dir} \
    --jobid ${SLURM_JOB_ID} \
    --eval_model ${eval_model} \
    --eval_only ${eval_only} \
    --max_token ${max_token} \
