# Backend Database Setup Specification

## Document Metadata

| Field | Value |
|---|---|
| Project | Adobe Stock AI Image Studio |
| Component | FastAPI Backend - Database Layer |
| Status | PENDING |
| Created | 2026-09-18 |

## Purpose

Initialize and configure the local SQLite database engine, session factory, and dependency injection mechanism for the FastAPI application. This module ensures reliable, concurrent-safe access to persistent storage throughout the image processing pipeline.

## Responsibilities

### Engine Initialization

The system must create a SQLAlchemy engine pointing to a local SQLite database file. The engine configuration must include the following settings:

| Setting | Value | Rationale |
|---|---|---|
| Database URL | Local file path using SQLite dialect | Single-node deployment with no external database dependency |
| WAL Mode | Enabled via PRAGMA on connect | Allows concurrent read operations during background audit tasks while a single writer holds the lock |
| Echo SQL | Disabled in production, configurable for development | Prevents log noise while allowing debugging when needed |
| Pool Pre-ping | Enabled | Ensures stale connections are detected before use |

### Session Factory Configuration

A session factory must be configured with the following parameters:

| Parameter | Value | Description |
|---|---|---|
| Autocommit | False | Transactions must be explicitly committed to prevent partial writes |
| Autoflush | False | Flushing is controlled manually to batch operations efficiently |
| Bind | The configured engine instance | All sessions derive from the same engine |
| Expire on Commit | True | Ensures objects reflect database state after commit |

### Dependency Injection

The database session must be provided to FastAPI endpoint handlers through a generator-based dependency function. This function must:

- Create a new session at the start of each request
- Yield the session to the endpoint handler
- Guarantee session closure in a finally block regardless of whether the request succeeds or raises an exception
- Be compatible with FastAPI's Depends mechanism for automatic injection

### Table Creation

All ORM model tables must be created automatically on application startup. The system must invoke the metadata creation method against the engine, ensuring that any new columns or tables defined in the ORM models are materialized in the SQLite file without requiring manual migration scripts during initial development.

## Constraints

| Constraint | Enforcement Strategy |
|---|---|
| Single-writer pattern | SQLite inherently enforces one writer at a time; the application must not attempt parallel write transactions |
| WAL mode enabled | Must be set via a connection event listener that executes the appropriate PRAGMA statement on every new connection |
| No raw SQL strings | All database interactions must go through the ORM or query builder; raw SQL is prohibited except for PRAGMA configuration |
| Session lifecycle bound to request | Sessions must never leak across requests or persist beyond the request-response cycle |
| Startup table creation | Tables must exist before any endpoint can receive traffic; creation runs synchronously during the application lifespan startup phase |