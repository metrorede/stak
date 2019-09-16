ALTER TABLE work_order ADD COLUMN attachment_id uuid UNIQUE REFERENCES attachment(id) ON UPDATE CASCADE;
