-- SQLite schema for simulated email database
CREATE TABLE emails (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sender TEXT NOT NULL,
    recipient TEXT NOT NULL,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    date TEXT NOT NULL,
    attachments TEXT, -- Comma-separated filenames
    is_read BOOLEAN,
    labels TEXT -- Comma-separated labels
);
