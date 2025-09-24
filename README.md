# Financial-data-
CREATE TABLE users (
  user_id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(255) NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE financial_records (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL,
  year SMALLINT NOT NULL,
  month TINYINT NOT NULL,              -- 1..12
  category VARCHAR(100),               -- optional (Income, Expense, etc)
  amount DECIMAL(15,2) NOT NULL,
  note TEXT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY user_year_month (user_id, year, month),
  FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);


