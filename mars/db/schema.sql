CREATE SCHEMA mars;

CREATE TABLE IF NOT EXISTS mars.apps (
    app_id SERIAL PRIMARY KEY,
    crawl_ver TEXT,
    pkg TEXT,
    name TEXT,
    version_name TEXT,
    version_code TEXT,
    category TEXT,
    num_downloads TEXT,
    platform_build_version_name TEXT,
    sdk_version TEXT,
    target_sdk_version TEXT,
    UNIQUE (crawl_ver, pkg)
);

CREATE TABLE IF NOT EXISTS mars.views (
    view_id SERIAL PRIMARY KEY,
    app_id INT REFERENCES mars.apps ON DELETE CASCADE,
    uuid TEXT NOT NULL,
    rico_cluster TEXT,
    xiaoyi_cluster TEXT,
    mars_cluster TEXT,
    UNIQUE (uuid)
);

CREATE TABLE IF NOT EXISTS mars.removed_views (
    removed_view_id SERIAL PRIMARY KEY,
    app_id INT REFERENCES mars.apps ON DELETE CASCADE,
    uuid TEXT NOT NULL,
    repl_uuid TEXT,
    reason TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS mars.failures (
    failure_id SERIAL PRIMARY KEY,
    view_id INT REFERENCES mars.views ON DELETE CASCADE,
    uuid TEXT,
    check_name TEXT,
    result_code TEXT,
    class_name TEXT,
    resource_id TEXT,
    content_desc TEXT,
    text TEXT,
    hint_text TEXT,
    bounds JSON,
    parent_bounds JSON,
    path TEXT,
    UNIQUE (uuid)
);

CREATE TABLE IF NOT EXISTS mars.labels (
    label_id SERIAL PRIMARY KEY,
    failure_id INT REFERENCES mars.failures ON DELETE CASCADE,
    label TEXT NOT NULL,
    source TEXT NOT NULL,
    conf REAL,
    UNIQUE (failure_id, label, source)
);

CREATE TABLE IF NOT EXISTS mars.repairs (
    repair_id SERIAL PRIMARY KEY,
    failure_id INT REFERENCES mars.failures ON DELETE CASCADE,
    repaired_cont_desc TEXT,
    repaired_text TEXT,
    repaired_hint_text TEXT,
    UNIQUE (failure_id)
);

DROP USER IF EXISTS mars_user;
CREATE USER mars_user WITH PASSWORD %s;
GRANT USAGE ON SCHEMA mars TO mars_user;
GRANT SELECT ON ALL TABLES IN SCHEMA mars TO mars_user;

CREATE INDEX pkg_idx ON mars.apps(pkg);
CREATE INDEX crawl_ver_idx ON mars.apps(crawl_ver);

CREATE INDEX app_id_idx ON mars.views(app_id);
CREATE INDEX view_uuid_idx ON mars.views(uuid);

CREATE INDEX view_id_idx ON mars.failures(view_id);
CREATE INDEX fail_uuid_idx ON mars.failures(uuid);
CREATE INDEX check_name_idx ON mars.failures(check_name);
CREATE INDEX result_code_idx ON mars.failures(result_code);

CREATE INDEX failure_id_idx ON mars.repairs(failure_id);
