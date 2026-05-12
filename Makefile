.PHONY: install run

install:
	pip install -r requirements.txt

run:
	uvicorn app.api:app --host 0.0.0.0 --port 8000 --reload
