#!/bin/bash
source activate ember
set -e
set -f
data_type="integ"
data_dir="" # folder directory to ember_qa_[reader_model].json file
correctness="true"
eval_only='false'
eval_model='gpt-4-turbo' # gpt-4-turbo, gpt-4-mini, gpt35, gpt-4o, Meta-Llama-3-70B-Instruct, Meta-Llama-3-8B-Instruct
scoring='yesno' # yesno
max_token=10

python run_qaeval.py --data_dir ${data_dir} \
    --data_type ${data_type} \
    --jobid ${SLURM_JOB_ID} \
    --eval_model ${eval_model} \
    --eval_only ${eval_only} \
    --scoring ${scoring} \
    --correctness ${correctness} \
    --max_token ${max_token} \
