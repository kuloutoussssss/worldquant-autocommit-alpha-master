@echo off
chcp 65001 >nul
cd /d D:\python_repo\worldquant-autocommit-alpha-master
python brain cli submit data\alphas\evcf_optimized.txt --universe TOP3000 --delay 1 --decay 0 --neutralization Industry --truncation 0.08 --name evcf_opt_v1
