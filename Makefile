# OfferLoop Makefile
# v1.0 — 常用命令快捷入口

.PHONY: help install dev-install test lint cov clean demo-empty run-all eval run-webhook run-approval

help:  ## 显示帮助信息
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install:  ## 安装运行时依赖
	pip install -e .

dev-install:  ## 安装开发依赖
	pip install -e ".[dev]"

test:  ## 运行测试
	python -m pytest tests/ -v

lint:  ## 代码检查
	python -m ruff check src/ tests/

cov:  ## 测试覆盖率
	python -m pytest tests/ --cov=src --cov-report=term-missing

clean:  ## 清理临时文件
	rm -rf __pycache__ src/**/__pycache__ tests/__pycache__
	rm -rf .pytest_cache
	rm -rf data/runs/*

demo-empty:  ## 空管道 smoke test
	python -c "from src.pipeline import run_full_pipeline; \
		run = run_full_pipeline(skip_embedding=True, skip_approval=True); \
		print(f'Run {run.run_id} complete: {run.stats().model_dump()}')"

run-all:  ## 运行完整管道
	python -c "from src.pipeline import run_full_pipeline; \
		run = run_full_pipeline(skip_approval=True); \
		print(f'Run {run.run_id} complete'); \
		stats = run.stats(); \
		print(f'Stats: {stats.model_dump()}')"

run-webhook:  ## 启动 Webhook 服务器
	python -m uvicorn src.inbox.webhook:create_app --factory --host 0.0.0.0 --port 8000 --reload

run-approval:  ## 启动 Streamlit 审批界面
	python -m streamlit run src/approval/app.py

run-approval-auto:  ## 管道模式（含审批交互）
	python -c "from src.pipeline import run_full_pipeline; \
		run = run_full_pipeline(skip_approval=False); \
		print(f'Run {run.run_id} complete'); \
		print(f'Pending approvals: {run.stats().pending}')"

eval:  ## 运行评估脚本
	python eval/run_eval.py

seed:  ## 生成 seed 数据集
	python -c "from src.inbox.csv_importer import import_csv; \
		import json; \
		fbs = import_csv('data/seed/feedback.csv'); \
		print(f'Loaded {len(fbs)} feedbacks from seed')"

docs-copy:  ## 复制架构文档到 docs/
	cp ai-*.md docs/ 2>/dev/null || echo "No ai-*.md files to copy"
