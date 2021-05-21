DATA_ROOT=/dataset/c07bd62b/superglue
GLUE_DATA_ROOT=/dataset/c07bd62b/glue_data
source config_tasks/model_blocklm_10B.sh
#source config_tasks/model_blocklm_roberta_large.sh
source $1

CHECKPOINT_PATH="/dataset/c07bd62b/finetune_checkpoints"

MASTER_PORT=$(shuf -n 1 -i 10000-65535)

OPTIONS_NCCL="NCCL_DEBUG=info NCCL_IB_DISABLE=0 NCCL_NET_GDR_LEVEL=2"
DISTRIBUTED_ARGS="${OPTIONS_NCCL} deepspeed --include localhost:2,3 --master_port $MASTER_PORT"
DATESTR=$(date +"%m-%d-%H-%M")

mkdir logs
run_cmd="${DISTRIBUTED_ARGS} finetune_gpt2.py \
       --deepspeed \
       --deepspeed_config config_tasks/config_blocklm_10B.json \
       --finetune \
       --experiment-name ${EXPERIMENT_NAME} \
       --task ${TASK_NAME} \
       --data-dir ${DATA_PATH} \
       --save ${CHECKPOINT_PATH} \
       --seq-length ${MAX_SEQ_LEN} \
       --checkpoint-activations \
       --eval-batch-size 16 \
       --save-epoch 100 \
       --num-workers 0 \
       --no-load-optim \
       --no-load-lr-scheduler \
       --fp16 \
       $MODEL_ARGS \
       $TRAIN_ARGS \
       $COMMON_ARGS \
       --epochs ${EPOCH_SINGLE} \
       --lr ${LR_SINGLE} \
       --overwrite \
       2>&1 | tee logs/log-${EXPERIMENT_NAME}.txt"

echo ${run_cmd}
eval ${run_cmd}
