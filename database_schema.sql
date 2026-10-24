-- ==========================================================
-- TradingAI Pro - Complete MySQL / MariaDB Database Schema
-- Ready for phpMyAdmin / MySQL 5.7+ / MySQL 8.0+ / MariaDB
-- ==========================================================

SET SQL_MODE = "NO_AUTO_VALUE_ON_ZERO";
START TRANSACTION;
SET time_zone = "+00:00";

CREATE DATABASE IF NOT EXISTS `tradingai_db` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE `tradingai_db`;

-- --------------------------------------------------------
-- 1. Table: users (المستخدمين وإدارة الحسابات)
-- --------------------------------------------------------
CREATE TABLE IF NOT EXISTS `users` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `uuid` VARCHAR(64) NOT NULL UNIQUE,
  `username` VARCHAR(100) NOT NULL UNIQUE,
  `email` VARCHAR(191) NULL UNIQUE,
  `password` VARCHAR(255) NULL,
  `access_code` VARCHAR(100) NOT NULL,
  `role` ENUM('admin', 'trader', 'vip_user', 'guest') NOT NULL DEFAULT 'trader',
  `status` ENUM('active', 'suspended', 'expired') NOT NULL DEFAULT 'active',
  `telegram_chat_id` VARCHAR(100) NULL,
  `last_login_at` TIMESTAMP NULL,
  `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  INDEX `idx_username` (`username`),
  INDEX `idx_access_code` (`access_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- --------------------------------------------------------
-- 2. Table: user_sessions (جلسات الدخول والـ Tokens)
-- --------------------------------------------------------
CREATE TABLE IF NOT EXISTS `user_sessions` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `token` VARCHAR(255) NOT NULL UNIQUE,
  `user_id` BIGINT UNSIGNED NOT NULL,
  `ip_address` VARCHAR(45) NULL,
  `user_agent` TEXT NULL,
  `expires_at` TIMESTAMP NOT NULL,
  `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- --------------------------------------------------------
-- 3. Table: activation_keys (مفاتيح وتراخيص VIP مع التوقيت الذكي)
-- --------------------------------------------------------
CREATE TABLE IF NOT EXISTS `activation_keys` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `code` VARCHAR(100) NOT NULL UNIQUE,
  `duration_hours` INT UNSIGNED NOT NULL DEFAULT 720,
  `duration_label` VARCHAR(150) NOT NULL,
  `label` VARCHAR(150) NOT NULL DEFAULT 'VIP License',
  `status` ENUM('PENDING', 'ACTIVE', 'EXPIRED', 'REVOKED') NOT NULL DEFAULT 'PENDING',
  `is_used` TINYINT(1) NOT NULL DEFAULT 0,
  `used_by_user_id` BIGINT UNSIGNED NULL,
  `activated_telegram_chat_id` VARCHAR(100) NULL,
  `activated_at` TIMESTAMP NULL,
  `expires_at` TIMESTAMP NULL,
  `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  INDEX `idx_code` (`code`),
  INDEX `idx_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- --------------------------------------------------------
-- 4. Table: ai_learning_memory (ذاكرة تعلم الذكاء الاصطناعي المستمرة)
-- --------------------------------------------------------
CREATE TABLE IF NOT EXISTS `ai_learning_memory` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `iteration_number` INT UNSIGNED NOT NULL,
  `asset_symbol` VARCHAR(30) NOT NULL,
  `action_recommended` ENUM('STRONG_BUY', 'BUY', 'NEUTRAL', 'SELL', 'STRONG_SELL') NOT NULL,
  `confidence_score` DECIMAL(5,2) NOT NULL,
  `setup_probability` DECIMAL(5,2) NOT NULL,
  `detected_pattern` VARCHAR(100) NOT NULL,
  `order_block_price` VARCHAR(100) NULL,
  `liquidity_sweep_price` VARCHAR(100) NULL,
  `market_bias` ENUM('Bullish', 'Bearish', 'Ranging') NOT NULL,
  `news_catalyst` VARCHAR(255) NULL,
  `macro_synthesis` TEXT NOT NULL,
  `actual_market_outcome` ENUM('PENDING', 'TARGET_HIT_TP1', 'TARGET_HIT_TP2', 'TARGET_HIT_TP3', 'STOP_LOSS_HIT') DEFAULT 'PENDING',
  `learning_accuracy_reward` DECIMAL(5,2) DEFAULT 0.00,
  `learned_notes` TEXT NULL,
  `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  INDEX `idx_asset_symbol` (`asset_symbol`),
  INDEX `idx_iteration` (`iteration_number`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- --------------------------------------------------------
-- 5. Table: trading_signals (إشارات التداول المؤسساتية SMC)
-- --------------------------------------------------------
CREATE TABLE IF NOT EXISTS `trading_signals` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `signal_uid` VARCHAR(100) NOT NULL UNIQUE,
  `symbol` VARCHAR(30) NOT NULL,
  `action` ENUM('BUY', 'SELL', 'STRONG_BUY', 'STRONG_SELL') NOT NULL,
  `timeframe` VARCHAR(20) NOT NULL DEFAULT '15m',
  `entry_price` DECIMAL(18,6) NOT NULL,
  `stop_loss` DECIMAL(18,6) NOT NULL,
  `tp1` DECIMAL(18,6) NOT NULL,
  `tp2` DECIMAL(18,6) NOT NULL,
  `tp3` DECIMAL(18,6) NOT NULL,
  `risk_reward_ratio` VARCHAR(20) NOT NULL DEFAULT '1:3.5',
  `confidence` DECIMAL(5,2) NOT NULL,
  `smc_setup_type` VARCHAR(100) NOT NULL,
  `session_name` VARCHAR(50) NOT NULL,
  `status` ENUM('ACTIVE', 'TP1_HIT', 'TP2_HIT', 'TP3_HIT', 'SL_HIT', 'CANCELLED', 'EXPIRED') NOT NULL DEFAULT 'ACTIVE',
  `sent_to_telegram` TINYINT(1) NOT NULL DEFAULT 0,
  `telegram_message_id` VARCHAR(100) NULL,
  `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  `closed_at` TIMESTAMP NULL,
  PRIMARY KEY (`id`),
  INDEX `idx_symbol_status` (`symbol`, `status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- --------------------------------------------------------
-- 6. Table: telegram_subscribers (مشتركو بوت التليجرام مع التراخيص)
-- --------------------------------------------------------
CREATE TABLE IF NOT EXISTS `telegram_subscribers` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `chat_id` VARCHAR(100) NOT NULL UNIQUE,
  `first_name` VARCHAR(150) NULL,
  `username` VARCHAR(150) NULL,
  `activation_code` VARCHAR(100) NOT NULL,
  `duration_label` VARCHAR(150) NOT NULL,
  `activated_at` TIMESTAMP NOT NULL,
  `expires_at` TIMESTAMP NOT NULL,
  `expired_notified` TINYINT(1) NOT NULL DEFAULT 0,
  `is_active` TINYINT(1) NOT NULL DEFAULT 1,
  `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  INDEX `idx_chat_id` (`chat_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- --------------------------------------------------------
-- 7. Table: telegram_logs (سجل الرسائل والإشعارات المرسلة)
-- --------------------------------------------------------
CREATE TABLE IF NOT EXISTS `telegram_logs` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `chat_id` VARCHAR(100) NOT NULL,
  `signal_id` BIGINT UNSIGNED NULL,
  `message_type` VARCHAR(50) NOT NULL DEFAULT 'SIGNAL',
  `message_content` TEXT NOT NULL,
  `status` ENUM('SUCCESS', 'FAILED') NOT NULL DEFAULT 'SUCCESS',
  `error_details` TEXT NULL,
  `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- --------------------------------------------------------
-- 8. Table: system_settings (إعدادات النظام العامة)
-- --------------------------------------------------------
CREATE TABLE IF NOT EXISTS `system_settings` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `setting_key` VARCHAR(100) NOT NULL UNIQUE,
  `setting_value` LONGTEXT NOT NULL,
  `description` VARCHAR(255) NULL,
  `updated_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ==========================================================
-- SEED DATA (بيانات أولية جاهزة للعمل فوراً)
-- ==========================================================

-- Insert Admin & VIP Users
INSERT INTO `users` (`uuid`, `username`, `email`, `access_code`, `role`, `status`) VALUES
('usr-admin-001', 'admin', 'admin@tradingai.pro', 'PRO-TRADER-2026-VIP', 'admin', 'active'),
('usr-vip-002', 'trader', 'trader@tradingai.pro', 'VIP-7777-2026', 'vip_user', 'active')
ON DUPLICATE KEY UPDATE `access_code`=VALUES(`access_code`);

-- Insert Master Activation Keys
INSERT INTO `activation_keys` (`code`, `duration_hours`, `duration_label`, `label`, `status`, `is_used`, `activated_at`, `expires_at`) VALUES
('PRO-TRADER-2026-VIP', 8760, 'سنة كاملة (VIP مدى الحياة)', 'Master Admin VIP Key', 'ACTIVE', 1, NOW(), DATE_ADD(NOW(), INTERVAL 365 DAY)),
('VIP-7777-2026', 720, 'شهر كامل (30 يوم)', 'VIP Trader Monthly Pass', 'ACTIVE', 1, NOW(), DATE_ADD(NOW(), INTERVAL 30 DAY)),
('VIP-GOLD-PASS-2026', 2160, '3 أشهر كاملة (90 يوم)', 'VIP Gold Pass', 'PENDING', 0, NULL, NULL)
ON DUPLICATE KEY UPDATE `status`=VALUES(`status`);

-- Insert Default System Settings
INSERT INTO `system_settings` (`setting_key`, `setting_value`, `description`) VALUES
('app_name', 'TradingAI Pro - Institutional SMC', 'اسم المنصة'),
('telegram_config', '{"botToken":"","chatId":"","enabled":true,"minConfidence":75,"assets":["XAU/USD","BTC/USDT","EUR/USD","GBP/USD","NVDA"],"notifyOnNews":true}', 'إعدادات تليجرام وبوت الإشعارات'),
('ai_learning_config', '{"continuousLearning":true,"recordOutcomes":true,"minConfidenceToLearn":70,"model":"gemini-pro-trading"}', 'إعدادات تعلم الذكاء الاصطناعي وحفظ الذاكرة')
ON DUPLICATE KEY UPDATE `setting_value`=VALUES(`setting_value`);

COMMIT;
