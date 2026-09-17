"""add vehicle telematics runtime table

Revision ID: runtime_0002
Revises: runtime_0001
Create Date: 2026-08-19 00:01:00+00:00
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "runtime_0002"
down_revision: Union[str, None] = "runtime_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "vehicle_telematics_timeseries",
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("vehicle_id", sa.Text(), nullable=False),
        sa.Column("vehicle_model_id", sa.Text(), nullable=False),
        sa.Column("vehicle_model_name", sa.Text(), nullable=False),
        sa.Column("variant", sa.Text(), nullable=False),
        sa.Column("production_batch_id", sa.Text(), nullable=False),
        sa.Column("supplier_lot_id", sa.Text(), nullable=False),
        sa.Column("plant_id", sa.Text(), nullable=False),
        sa.Column("production_line_id", sa.Text(), nullable=False),
        sa.Column("odometer_km", sa.Double(), nullable=False),
        sa.Column("vehicle_speed_kph", sa.Double(), nullable=False),
        sa.Column("ambient_temperature_c", sa.Double(), nullable=False),
        sa.Column("battery_temperature_c", sa.Double(), nullable=False),
        sa.Column("battery_soc_pct", sa.Double(), nullable=False),
        sa.Column("battery_voltage_v", sa.Double(), nullable=False),
        sa.Column("battery_current_a", sa.Double(), nullable=False),
        sa.Column("battery_internal_resistance_ohm", sa.Double(), nullable=False),
        sa.Column("transmission_temperature_c", sa.Double(), nullable=False),
        sa.Column("transmission_slip_ms", sa.Double(), nullable=False),
        sa.Column("torque_converter_slip_rpm", sa.Double(), nullable=False),
        sa.Column("steering_torque_nm", sa.Double(), nullable=False),
        sa.Column("steering_angle_deg", sa.Double(), nullable=False),
        sa.Column("vehicle_vibration_mm_s", sa.Double(), nullable=False),
        sa.Column("vertical_acceleration_g", sa.Double(), nullable=False),
        sa.Column("lateral_acceleration_g", sa.Double(), nullable=False),
        sa.Column("road_roughness_index", sa.Double(), nullable=False),
        sa.Column("impact_g_force", sa.Double(), nullable=False),
        sa.Column("dtc_count", sa.BigInteger(), nullable=False),
        sa.Column("warning_flag", sa.Boolean(), nullable=False),
        sa.Column("data_origin", sa.Text(), nullable=False),
        sa.Column("generator_version", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["vehicle_model_id"], ["vehicle_models.vehicle_model_id"],
            name=op.f("fk_runtime_vehicle_telematics_timeseries_vehicle_model_id_vehicle_models"),
            onupdate="RESTRICT", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["production_batch_id"], ["production_batches.production_batch_id"],
            name=op.f("fk_runtime_vehicle_telematics_timeseries_production_batch_id_production_batches"),
            onupdate="RESTRICT", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["supplier_lot_id"], ["supplier_lots.supplier_lot_id"],
            name=op.f("fk_runtime_vehicle_telematics_timeseries_supplier_lot_id_supplier_lots"),
            onupdate="RESTRICT", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["plant_id"], ["plants.plant_id"],
            name=op.f("fk_runtime_vehicle_telematics_timeseries_plant_id_plants"),
            onupdate="RESTRICT", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["production_line_id"], ["production_lines.production_line_id"],
            name=op.f("fk_runtime_vehicle_telematics_timeseries_production_line_id_production_lines"),
            onupdate="RESTRICT", ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "timestamp", "vehicle_id",
            name=op.f("pk_runtime_vehicle_telematics_timeseries"),
        ),
    )


def downgrade() -> None:
    op.drop_table("vehicle_telematics_timeseries")
