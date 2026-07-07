# Configuration
API_KEY=""
BASE_URL=""
MODEL_NAME=""
JINA_API_KEY=""
SERPER_API_KEY=""
BENCHMARK_DATA_PATH="./bench_data/question.jsonl"


WORKERS=4
ENABLE_THINKING=true # if use thinking mode 



export SUMMARY_API_KEY=$API_KEY # We use the same model for webpage summarization
export SUMMARY_API_BASE_URL=$BASE_URL
export SUMMARY_MODEL_NAME=$MODEL_NAME
export JINA_API_KEY=$JINA_API_KEY
export SERPER_API_KEY=$SERPER_API_KEY

D:/anaconda3/python.exe run_benchmark.py \
    --num_workers "$WORKERS" \
    --output_dir ./benchmark_results \
    --api_key "$API_KEY" \
    --base_url "$BASE_URL" \
    --model_name "$MODEL_NAME" \
    --enable_thinking "$ENABLE_THINKING" \
    --benchmark_data_path "$BENCHMARK_DATA_PATH"
