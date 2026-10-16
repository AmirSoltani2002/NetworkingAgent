from datetime import datetime, timezone
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator, field_validator
from .zsk_model import MEASURED

UNITS = dict(zip(MEASURED, ['rpm','%','A','kW','mm/s','degC','degC','degC','bar','kg/h']))
class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
class Measurement(Strict):
    timestamp: datetime
    machine_id: str = Field(min_length=1,max_length=80)
    @field_validator('machine_id')
    @classmethod
    def machine_code(cls,value):
        # Bounded server-side character validation; discovery avoids regex schemas
        # that the existing generic harness intentionally refuses.
        if not all(c.isascii() and (c.isalnum() or c in '_.-') for c in value):
            raise ValueError('Machine ID must contain only ASCII letters, digits, underscore, dot or dash')
        return value
    recipe: Literal['A','B','C']
    screw_speed_rpm: float = Field(ge=0,le=5000)
    screw_torque_pct: float = Field(ge=0,le=300)
    motor_current_a: float = Field(ge=0,le=20000)
    motor_power_kw: float = Field(ge=0,le=20000)
    gearbox_vibration_rms_mm_s: float = Field(ge=0,le=1000)
    gearbox_oil_temp_c: float = Field(ge=-50,le=500)
    barrel_zone_temp_c: float = Field(ge=-50,le=1000)
    melt_temp_c: float = Field(ge=-50,le=1000)
    melt_pressure_bar: float = Field(ge=0,le=3000)
    feed_rate_kg_h: float = Field(ge=0,le=100000)
    alarm_active: Literal[0,1] = 0
    @field_validator('timestamp')
    @classmethod
    def utc(cls,value):
        # Supplied CSV timestamps are naive: explicitly interpret them as UTC.
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    def row(self):
        result=self.model_dump();result['timestamp']=self.timestamp.replace(tzinfo=None).isoformat();return result
class Reading(Measurement):
    units: dict[str,str]
    provenance: Literal['unknown','synthetic','verified_operator_label'] = 'unknown'
    health_label: Literal[0,1] | None = None
    @model_validator(mode='after')
    def verified(self):
        if self.units != UNITS:
            raise ValueError('Units must exactly match the documented units for all ten signals')
        if self.health_label is not None and self.provenance != 'verified_operator_label':
            raise ValueError('A ground-truth label requires verified_operator_label provenance')
        if self.health_label is None and self.provenance == 'verified_operator_label':
            raise ValueError('Verified label provenance requires health_label')
        return self
class AddInput(Strict):
    readings: list[Reading] = Field(min_length=1,max_length=100)
    idempotency_key: str = Field(min_length=8,max_length=120,pattern=r'^[A-Za-z0-9_.:-]+$')
class EvaluationConfig(Strict):
    test_fraction: float = Field(default=.2,ge=.1,le=.4)
    gap: int = Field(default=20,ge=2,le=100)
class TrainInput(Strict):
    idempotency_key: str = Field(min_length=8,max_length=120,pattern=r'^[A-Za-z0-9_.:-]+$')
    evaluation_config: EvaluationConfig = Field(default_factory=EvaluationConfig)
class Filters(Strict):
    machine_id: str | None = Field(default=None,min_length=1,max_length=80)
    start_time: datetime | None = None
    end_time: datetime | None = None
    page: int = Field(default=1,ge=1,le=100000)
    page_size: int = Field(default=50,ge=1,le=100)
    @model_validator(mode='after')
    def dates(self):
        for key in ('start_time','end_time'):
            value=getattr(self,key)
            if value:
                setattr(self,key,Measurement.utc(value).replace(tzinfo=None))
        if self.start_time and self.end_time and self.start_time > self.end_time:
            raise ValueError('start_time must precede end_time')
        return self
class BatchInput(Filters):
    source: Literal['unlabeled','labeled'] = 'unlabeled'
    idempotency_key: str = Field(min_length=8,max_length=120,pattern=r'^[A-Za-z0-9_.:-]+$')
class PredictInput(Strict):
    measurement: Measurement | None = None
    measurement_id: int | None = Field(default=None,ge=1)
    source: Literal['unlabeled','labeled'] = 'unlabeled'
    recent_history: list[Measurement] | None = Field(default=None,max_length=2)
    @model_validator(mode='after')
    def target(self):
        if (self.measurement is None)==(self.measurement_id is None):
            raise ValueError('Supply exactly one of measurement or measurement_id')
        return self
class RollbackInput(Strict):
    model_version: str
    idempotency_key: str = Field(min_length=8,max_length=120,pattern=r'^[A-Za-z0-9_.:-]+$')
