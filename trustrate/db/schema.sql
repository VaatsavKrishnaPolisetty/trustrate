CREATE TABLE IF NOT EXISTS users (
 id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
 email VARCHAR(254) NOT NULL UNIQUE, name VARCHAR(100) NOT NULL,
 password_hash VARCHAR(255) NOT NULL, role ENUM('user','admin') NOT NULL DEFAULT 'user',
 created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS products (
 id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY, slug VARCHAR(100) NOT NULL UNIQUE,
 name VARCHAR(200) NOT NULL, description TEXT NOT NULL,
 created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS reviews (
 id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
 product_id BIGINT UNSIGNED NOT NULL, user_id BIGINT UNSIGNED NOT NULL,
 rating TINYINT UNSIGNED NOT NULL, title VARCHAR(200) NOT NULL, body TEXT NOT NULL,
 status ENUM('pending_score','published','flagged','watch','removed','restored','deleted') NOT NULL DEFAULT 'pending_score',
 ip_hash CHAR(64) NOT NULL, ip_prefix VARCHAR(64) NOT NULL DEFAULT '', user_agent VARCHAR(512) NOT NULL DEFAULT '',
 revision INT UNSIGNED NOT NULL DEFAULT 1,
 is_synthetic BOOLEAN NOT NULL DEFAULT FALSE, true_label VARCHAR(40) NULL,
 scenario VARCHAR(80) NULL, split VARCHAR(20) NULL, source_id VARCHAR(100) NULL UNIQUE,
 created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
 updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
 FOREIGN KEY(product_id) REFERENCES products(id), FOREIGN KEY(user_id) REFERENCES users(id),
 CHECK(rating BETWEEN 1 AND 5), INDEX(product_id,status), INDEX(user_id,created_at), INDEX(ip_hash,created_at)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS review_scores (
 review_id BIGINT UNSIGNED PRIMARY KEY, review_revision INT UNSIGNED NOT NULL,
 classical_score DOUBLE NOT NULL, quantum_score DOUBLE NOT NULL, hybrid_score DOUBLE NOT NULL,
 label VARCHAR(40) NOT NULL, reasons JSON NOT NULL, backend VARCHAR(100) NOT NULL,
 model_version VARCHAR(100) NOT NULL, ibm_job_id VARCHAR(255) NULL, scored_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
 FOREIGN KEY(review_id) REFERENCES reviews(id) ON DELETE CASCADE
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS admin_actions (
 id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY, admin_id BIGINT UNSIGNED NOT NULL,
 review_id BIGINT UNSIGNED NOT NULL, action ENUM('remove','restore','watch','inject') NOT NULL,
 previous_status VARCHAR(20) NOT NULL, reason VARCHAR(500) NOT NULL,
 created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
 FOREIGN KEY(admin_id) REFERENCES users(id), FOREIGN KEY(review_id) REFERENCES reviews(id)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS scoring_queue (
 review_id BIGINT UNSIGNED PRIMARY KEY, revision INT UNSIGNED NOT NULL,
 attempts INT UNSIGNED NOT NULL DEFAULT 0, available_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
 locked_until TIMESTAMP NULL, last_error VARCHAR(200) NULL,
 FOREIGN KEY(review_id) REFERENCES reviews(id) ON DELETE CASCADE,
 INDEX(available_at,locked_until)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS rate_limits (
 bucket CHAR(64) PRIMARY KEY, hits INT UNSIGNED NOT NULL DEFAULT 0, expires_at BIGINT NOT NULL,
 INDEX(expires_at)
) ENGINE=InnoDB;
INSERT IGNORE INTO products(id,slug,name,description) VALUES
 (1,'aurora-headphones','Aurora Wireless Headphones','Comfortable wireless audio for everyday listening. Share your experience and compare the raw rating with the scored review signal.');
