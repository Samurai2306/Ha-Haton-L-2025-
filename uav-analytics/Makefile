.PHONY: etl api dev

etl:
	python3 app.py && python3 etl_from_csv.py

api:
	uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

dev:
	cd web && npm run dev

