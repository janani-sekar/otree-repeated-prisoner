#!/bin/sh

#SBATCH --account=pi-misra
#SBATCH --partition=standard
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=00-04:00:00
#SBATCH --job-name=s0_neural_baselines
#SBATCH --output=/project/caai_cdnn/janani/discovering_dynamic_games/logs/%x_%j.out
#SBATCH --error=/project/caai_cdnn/janani/discovering_dynamic_games/logs/%x_%j.err

module load python/booth/3.12

cd /project/caai_cdnn/janani/discovering_dynamic_games/
source .venv/bin/activate

export PYTHONUNBUFFERED=1

python3 code/s0_predictive_baselines.py \
    --data data/otree_fudenberg/experimental_data.csv \
    --outdir results/next_action_prediction \
    --n-bootstrap 1000 \
    --seed 0
