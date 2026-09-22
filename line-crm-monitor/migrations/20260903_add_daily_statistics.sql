CREATE TABLE IF NOT EXISTS daily_statistics (
    server_id   TEXT    NOT NULL,
    device_id   TEXT    NOT NULL,
    stat_date   DATE    NOT NULL,              -- Asia/Taipei 自然日
    success     INTEGER NOT NULL DEFAULT 0,
    fail        INTEGER NOT NULL DEFAULT 0,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (server_id, device_id, stat_date)
);

CREATE INDEX IF NOT EXISTS idx_daily_stat_date_server
    ON daily_statistics (stat_date, server_id);
