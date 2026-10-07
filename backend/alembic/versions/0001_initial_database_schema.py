"""initial database schema

Revision ID: 0001
Revises: 
Create Date: 2026-10-02 16:00:26.990029
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0001'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the initial claims intake schema."""
    op.create_table('audit_logs',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('entity_type', sa.String(length=64), nullable=False),
    sa.Column('entity_id', sa.String(length=128), nullable=False),
    sa.Column('action', sa.String(length=64), nullable=False),
    sa.Column('changes', sa.JSON(), nullable=False),
    sa.Column('actor', sa.String(length=64), nullable=True),
    sa.Column('timestamp', sa.DateTime(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('policies',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('policy_number', sa.String(length=64), nullable=False),
    sa.Column('holder_name', sa.String(length=255), nullable=False),
    sa.Column('plan_type', sa.String(length=64), nullable=False),
    sa.Column('effective_date', sa.Date(), nullable=False),
    sa.Column('expiration_date', sa.Date(), nullable=False),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('document_path', sa.String(length=512), nullable=True),
    sa.Column('parsed_markdown', sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_policies_policy_number'), 'policies', ['policy_number'], unique=True)
    op.create_table('claims',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('claim_number', sa.String(length=32), nullable=False),
    sa.Column('status', sa.Enum('SUBMITTED', 'INTAKE', 'PROCESSING', 'TRIAGED', 'UNDER_REVIEW', 'APPROVED', 'DENIED', 'ESCALATED', name='claimstatus'), nullable=False),
    sa.Column('raw_text', sa.Text(), nullable=False),
    sa.Column('uploaded_images', sa.JSON(), nullable=False),
    sa.Column('claimant_name', sa.String(length=255), nullable=True),
    sa.Column('policy_number', sa.String(length=64), nullable=True),
    sa.Column('policy_id', sa.UUID(), nullable=True),
    sa.Column('incident_date', sa.Date(), nullable=True),
    sa.Column('incident_description', sa.Text(), nullable=True),
    sa.Column('injury_type', sa.String(length=128), nullable=True),
    sa.Column('body_part_affected', sa.String(length=128), nullable=True),
    sa.Column('treatment_received', sa.Text(), nullable=True),
    sa.Column('provider_name', sa.String(length=255), nullable=True),
    sa.Column('estimated_amount', sa.Float(), nullable=True),
    sa.Column('priority', sa.String(length=32), nullable=True),
    sa.Column('confidence_score', sa.Float(), nullable=True),
    sa.Column('requires_human_review', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['policy_id'], ['policies.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_claims_claim_number'), 'claims', ['claim_number'], unique=True)
    op.create_index(op.f('ix_claims_policy_number'), 'claims', ['policy_number'], unique=False)
    op.create_table('policy_coverages',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('policy_id', sa.UUID(), nullable=False),
    sa.Column('coverage_type', sa.String(length=128), nullable=False),
    sa.Column('covered_services', sa.JSON(), nullable=False),
    sa.Column('exclusions', sa.JSON(), nullable=False),
    sa.Column('deductible', sa.Float(), nullable=False),
    sa.Column('copay', sa.Float(), nullable=False),
    sa.Column('coinsurance_percent', sa.Float(), nullable=False),
    sa.Column('out_of_pocket_max', sa.Float(), nullable=False),
    sa.Column('annual_limit', sa.Float(), nullable=True),
    sa.ForeignKeyConstraint(['policy_id'], ['policies.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('claim_assessments',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('claim_id', sa.UUID(), nullable=False),
    sa.Column('intake_result', sa.JSON(), nullable=False),
    sa.Column('triage_result', sa.JSON(), nullable=False),
    sa.Column('policy_check_result', sa.JSON(), nullable=False),
    sa.Column('fraud_signals', sa.JSON(), nullable=False),
    sa.Column('medical_codes', sa.JSON(), nullable=False),
    sa.Column('duplicate_check', sa.JSON(), nullable=False),
    sa.Column('summary', sa.Text(), nullable=True),
    sa.Column('assessment_report', sa.Text(), nullable=True),
    sa.Column('agent_reasoning_trace', sa.JSON(), nullable=False),
    sa.ForeignKeyConstraint(['claim_id'], ['claims.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('claim_id')
    )
    op.create_table('claim_events',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('claim_id', sa.UUID(), nullable=False),
    sa.Column('event_type', sa.String(length=64), nullable=False),
    sa.Column('agent_name', sa.String(length=64), nullable=True),
    sa.Column('details', sa.JSON(), nullable=False),
    sa.Column('timestamp', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['claim_id'], ['claims.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('human_reviews',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('claim_id', sa.UUID(), nullable=False),
    sa.Column('reviewer_id', sa.String(length=64), nullable=False),
    sa.Column('decision', sa.String(length=32), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['claim_id'], ['claims.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('review_decisions',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('review_id', sa.UUID(), nullable=False),
    sa.Column('action_taken', sa.String(length=64), nullable=False),
    sa.Column('timestamp', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['review_id'], ['human_reviews.id'], ),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    """Remove tables in dependency order and release the PostgreSQL enum."""
    op.drop_table('review_decisions')
    op.drop_table('human_reviews')
    op.drop_table('claim_events')
    op.drop_table('claim_assessments')
    op.drop_table('policy_coverages')
    op.drop_index(op.f('ix_claims_policy_number'), table_name='claims')
    op.drop_index(op.f('ix_claims_claim_number'), table_name='claims')
    op.drop_table('claims')
    sa.Enum(name='claimstatus').drop(op.get_bind(), checkfirst=True)
    op.drop_index(op.f('ix_policies_policy_number'), table_name='policies')
    op.drop_table('policies')
    op.drop_table('audit_logs')
