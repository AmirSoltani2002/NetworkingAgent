from sqlalchemy import func, select

from .db import Product
from .errors import ServiceError
from .schemas import FEATURES


class DatasetService:
    def __init__(self, sessions, model, settings):
        self.sessions, self.model, self.settings = sessions, model, settings

    def query(self, filters):
        if filters.quality_label is not None:
            raise ServiceError("LABELS_REMOVED", "Ground-truth labels are no longer stored on production records")
        query = select(Product)
        for field in ["machine_id"]:
            value = getattr(filters, field)
            if value is not None:
                query = query.where(getattr(Product, field) == value)
        if filters.start_date:
            query = query.where(Product.production_timestamp >= filters.start_date)
        if filters.end_date:
            query = query.where(Product.production_timestamp <= filters.end_date)
        return query

    @staticmethod
    def public(row):
        return {"id": row.id, "product_id": row.product_id, "machine_id": row.machine_id,
                "production_timestamp": row.production_timestamp.isoformat(),
                **{key: getattr(row, key) for key in FEATURES}}

    def records(self, filters):
        if filters.predicted_label is not None:
            raise ServiceError("INVALID_FILTER", "Use the predictions endpoint for predicted-label filtering")
        query = self.query(filters)
        with self.sessions() as session:
            total = session.scalar(select(func.count()).select_from(query.subquery()))
            records = session.scalars(query.order_by(Product.id).offset(filters.offset).limit(filters.limit)).all()
        return {"items": [self.public(r) for r in records], "total": total, "limit": filters.limit, "offset": filters.offset,
                "synthetic": True}

    def predictions(self, filters):
        with self.sessions() as session:
            records = session.scalars(self.query(filters).order_by(Product.id).limit(self.settings.max_dataset_size+1)).all()
        if len(records) > self.settings.max_dataset_size:
            raise ServiceError("DATASET_LIMIT", "Narrow the filters before classifying this dataset", 413)
        # Statistics cover the complete filtered population, with pagination after prediction filtering.
        predictions = self.model.predict([{k: getattr(r, k) for k in FEATURES} for r in records]) if records else []
        version = predictions[0]["model_version"] if predictions else self.model.bundle()["model_version"]
        items = [{"product_id": r.product_id, "machine_id": r.machine_id, **p} for r, p in zip(records, predictions)]
        defective = sum(p["predicted_label"] == 0 for p in predictions)
        summary = {"population_count": len(records), "predicted_defective": defective, "predicted_good": len(records)-defective,
                   "note": "Ground-truth labels are not stored with production records; use held-out model metrics for evaluation"}
        if filters.predicted_label is not None:
            items = [r for r in items if r["predicted_label"] == filters.predicted_label]
        total = len(items)
        return {"items": items[filters.offset:filters.offset+filters.limit], "total": total, "limit": filters.limit,
                "offset": filters.offset, "has_more": filters.offset+filters.limit < total,
                "statistics": summary, "model_version": version, "synthetic": True}

    def statistics(self):
        with self.sessions() as session:
            rows = session.execute(select(Product.machine_id, func.count()).group_by(Product.machine_id)).all()
        return {"total": sum(r[1] for r in rows), "synthetic": True,
                "machines": [{"machine_id": r[0], "count": r[1]} for r in rows]}
