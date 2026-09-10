import uuid
from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base

def utcnow(): return datetime.now(timezone.utc)

class Organization(Base):
    __tablename__='organizations'
    id: Mapped[int]=mapped_column(Integer, primary_key=True)
    code: Mapped[str]=mapped_column(String(80), unique=True, nullable=False)
    name: Mapped[str]=mapped_column(String(255), nullable=False)
    description: Mapped[str|None]=mapped_column(Text)
    parent_id: Mapped[int|None]=mapped_column(ForeignKey('organizations.id'))
    is_active: Mapped[bool]=mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

class AppUser(Base):
    __tablename__='app_users'
    id: Mapped[int]=mapped_column(Integer, primary_key=True)
    email: Mapped[str]=mapped_column(String(255), unique=True, nullable=False)
    display_name: Mapped[str]=mapped_column(String(255), nullable=False)
    is_active: Mapped[bool]=mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=utcnow)

class OrganizationMembership(Base):
    __tablename__='organization_memberships'
    __table_args__=(UniqueConstraint('user_id','organization_id',name='uq_user_org'),)
    id: Mapped[int]=mapped_column(Integer, primary_key=True)
    user_id: Mapped[int]=mapped_column(ForeignKey('app_users.id'), nullable=False)
    organization_id: Mapped[int]=mapped_column(ForeignKey('organizations.id'), nullable=False)
    role: Mapped[str]=mapped_column(String(40), nullable=False)
    is_active: Mapped[bool]=mapped_column(Boolean, default=True, nullable=False)
    user=relationship('AppUser')
    organization=relationship('Organization')

class CatalogSystem(Base):
    __tablename__='catalog_systems'
    __table_args__=(UniqueConstraint('organization_id','name',name='uq_system_org_name'),)
    id: Mapped[int]=mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int]=mapped_column(ForeignKey('organizations.id'), nullable=False)
    name: Mapped[str]=mapped_column(String(255), nullable=False)
    business_purpose: Mapped[str|None]=mapped_column(Text)
    description: Mapped[str|None]=mapped_column(Text)
    vendor: Mapped[str|None]=mapped_column(String(255))
    system_owner: Mapped[str|None]=mapped_column(String(255))
    lifecycle_status: Mapped[str]=mapped_column(String(40), default='ACTIVE', nullable=False)
    created_by: Mapped[int|None]=mapped_column(ForeignKey('app_users.id'))

class DataAsset(Base):
    __tablename__='data_assets'
    id: Mapped[int]=mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int]=mapped_column(ForeignKey('organizations.id'), nullable=False)
    asset_identifier: Mapped[str]=mapped_column(String(36), default=lambda: str(uuid.uuid4()), unique=True, nullable=False)
    name: Mapped[str]=mapped_column(String(255), nullable=False)
    business_definition: Mapped[str|None]=mapped_column(Text)
    business_domain: Mapped[str|None]=mapped_column(String(255))
    business_owner: Mapped[str|None]=mapped_column(String(255))
    data_steward: Mapped[str|None]=mapped_column(String(255))
    authoritative_status: Mapped[str]=mapped_column(String(40), default='UNKNOWN', nullable=False)
    asset_status: Mapped[str]=mapped_column(String(40), default='ACTIVE', nullable=False)
    created_by: Mapped[int|None]=mapped_column(ForeignKey('app_users.id'))
    resources=relationship('AssetResource', cascade='all, delete-orphan')
    metadata_items=relationship('AssetMetadata', cascade='all, delete-orphan')
    publication=relationship('AssetPublication', uselist=False, cascade='all, delete-orphan')

class DataResource(Base):
    __tablename__='data_resources'
    id: Mapped[int]=mapped_column(Integer, primary_key=True)
    organization_id: Mapped[int]=mapped_column(ForeignKey('organizations.id'), nullable=False)
    system_id: Mapped[int|None]=mapped_column(ForeignKey('catalog_systems.id'))
    name: Mapped[str]=mapped_column(String(255), nullable=False)
    resource_type: Mapped[str]=mapped_column(String(80), nullable=False)
    structure_type: Mapped[str]=mapped_column(String(40), nullable=False)
    description: Mapped[str|None]=mapped_column(Text)
    location_reference: Mapped[str|None]=mapped_column(Text)
    format: Mapped[str|None]=mapped_column(String(100))
    media_type: Mapped[str|None]=mapped_column(String(150))
    created_by: Mapped[int|None]=mapped_column(ForeignKey('app_users.id'))
    system=relationship('CatalogSystem')

class AssetResource(Base):
    __tablename__='asset_resources'
    __table_args__=(UniqueConstraint('asset_id','resource_id',name='uq_asset_resource'),)
    id: Mapped[int]=mapped_column(Integer, primary_key=True)
    asset_id: Mapped[int]=mapped_column(ForeignKey('data_assets.id',ondelete='CASCADE'), nullable=False)
    resource_id: Mapped[int]=mapped_column(ForeignKey('data_resources.id',ondelete='CASCADE'), nullable=False)
    relationship_type: Mapped[str]=mapped_column(String(80), default='REPRESENTATION', nullable=False)
    is_authoritative: Mapped[bool]=mapped_column(Boolean, default=False, nullable=False)
    resource=relationship('DataResource')

class AssetMetadata(Base):
    __tablename__='asset_metadata'
    id: Mapped[int]=mapped_column(Integer, primary_key=True)
    asset_id: Mapped[int]=mapped_column(ForeignKey('data_assets.id',ondelete='CASCADE'), nullable=False)
    metadata_key: Mapped[str]=mapped_column(String(120), nullable=False)
    metadata_value: Mapped[object]=mapped_column(JSON, nullable=False)
    metadata_source: Mapped[str]=mapped_column(String(40), default='USER', nullable=False)
    review_status: Mapped[str]=mapped_column(String(40), default='APPROVED', nullable=False)
    created_by: Mapped[int|None]=mapped_column(ForeignKey('app_users.id'))

class AssetPublication(Base):
    __tablename__='asset_publications'
    id: Mapped[int]=mapped_column(Integer, primary_key=True)
    asset_id: Mapped[int]=mapped_column(ForeignKey('data_assets.id',ondelete='CASCADE'), unique=True, nullable=False)
    status: Mapped[str]=mapped_column(String(40), default='DRAFT', nullable=False)
    submitted_by: Mapped[int|None]=mapped_column(ForeignKey('app_users.id'))
    submitted_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    approved_by: Mapped[int|None]=mapped_column(ForeignKey('app_users.id'))
    approved_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    validation_errors: Mapped[object|None]=mapped_column(JSON)

class AssetRelease(Base):
    __tablename__='asset_releases'
    __table_args__=(UniqueConstraint('asset_id','version_number',name='uq_asset_release'),)
    id: Mapped[int]=mapped_column(Integer, primary_key=True)
    asset_id: Mapped[int]=mapped_column(ForeignKey('data_assets.id'), nullable=False)
    version_number: Mapped[int]=mapped_column(Integer, nullable=False)
    snapshot: Mapped[dict]=mapped_column(JSON, nullable=False)
    snapshot_hash: Mapped[str|None]=mapped_column(String(128))
    approved_by: Mapped[int|None]=mapped_column(ForeignKey('app_users.id'))
    approved_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    ckan_dataset_id: Mapped[str|None]=mapped_column(String(255))
    ckan_name: Mapped[str|None]=mapped_column(String(255))
    publication_result: Mapped[object|None]=mapped_column(JSON)

class PublicationEvent(Base):
    __tablename__='publication_events'
    id: Mapped[int]=mapped_column(Integer, primary_key=True)
    asset_id: Mapped[int]=mapped_column(ForeignKey('data_assets.id'), nullable=False)
    event_type: Mapped[str]=mapped_column(String(80), nullable=False)
    from_status: Mapped[str|None]=mapped_column(String(40))
    to_status: Mapped[str|None]=mapped_column(String(40))
    performed_by: Mapped[int|None]=mapped_column(ForeignKey('app_users.id'))
    comments: Mapped[str|None]=mapped_column(Text)
    event_metadata: Mapped[object|None]=mapped_column(JSON)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=utcnow)
