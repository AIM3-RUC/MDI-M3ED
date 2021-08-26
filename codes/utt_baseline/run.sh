# eg:
# bash run.sh V 0 1
export PYTHONPATH=/data9/MEmoConv
set -e
modality=$1 # 
gpu=$2
run_ind=$3
for run_idx in $run_ind;
do
    cmd="python run_baseline.py --gpu_id $gpu --modality=$modality 
        --dataset_mode chmed
        --pretained_ft_type utt_baseline
        --num_threads 0 --run_idx=$run_idx
        --max_epoch 30 --patience 5 --warmup_epoch 5 
        --dropout_rate 0.5  --learning_rate 1e-3 --batch_size 64 --postfix self
        --v_ft_type denseface --v_input_size 342 --max_text_tokens 50
        --a_ft_type wav2vec_zh --a_input_size 1024 --max_acoustic_tokens 128
        --l_ft_type bert_base_chinese --l_input_size 768 --max_visual_tokens 64
        --l_hidden_size 256 --v_hidden_size 256 --a_hidden_size 256 --mid_fusion_layers '512,256'
    "
    echo "\n-------------------------------------------------------------------------------------"
    echo "Execute command: $cmd"
    echo "-------------------------------------------------------------------------------------\n"
    echo $cmd | sh
done