-- Scobility MySQL schema
-- Run in order: Catalog → Chart → Player → Relationship → Score

CREATE TABLE `Catalog` (
  `catalog_id`     INT           NOT NULL AUTO_INCREMENT,
  `name`           VARCHAR(100)  NOT NULL,
  `active`         TINYINT(1)    NOT NULL DEFAULT 1,
  `last_update`    DATETIME      NULL,
  `perfect_offset` DOUBLE        NULL,
  `perfect_score`  DOUBLE        NULL,
  PRIMARY KEY (`catalog_id`),
  UNIQUE KEY `uq_catalog_name` (`name`)
);

CREATE TABLE `Chart` (
  `global_chart_id`  INT           NOT NULL AUTO_INCREMENT,
  `catalog_id`       INT           NOT NULL,
  `chart_id`         INT           NOT NULL,
  `hash`             VARCHAR(64)   NOT NULL,
  `title`            VARCHAR(255)  NULL,
  `subtitle`         VARCHAR(255)  NULL,
  `artist`           VARCHAR(255)  NULL,
  `meter`            DOUBLE        NULL,
  `slot`             VARCHAR(50)   NULL,
  `style`            VARCHAR(20)   NULL,
  `value`            DOUBLE        NULL,
  `value_scoring`    DOUBLE        NULL,
  `value_passing`    DOUBLE        NULL,
  `spice`            DOUBLE        NULL,
  `spice_calc_time`  DATETIME      NULL,
  PRIMARY KEY (`global_chart_id`),
  UNIQUE KEY `uq_chart_in_catalog` (`catalog_id`, `chart_id`),
  KEY `idx_chart_hash` (`hash`),
  CONSTRAINT `fk_chart_catalog`
    FOREIGN KEY (`catalog_id`) REFERENCES `Catalog` (`catalog_id`)
);

CREATE TABLE `Player` (
  `performance_id`      INT           NOT NULL AUTO_INCREMENT,
  `catalog_id`          INT           NOT NULL,
  `entrant_id`          INT           NOT NULL,
  `groovestats_id`      INT           NOT NULL,
  `boogiestats_id`      INT           NULL,
  `name`                VARCHAR(255)  NULL,
  `scobility`           DOUBLE        NULL,
  `timing_power`        DOUBLE        NULL,
  `comfort_zone`        DOUBLE        NULL,
  `scobility_calc_time` DATETIME      NULL,
  PRIMARY KEY (`performance_id`),
  UNIQUE KEY `uq_player_in_catalog` (`catalog_id`, `entrant_id`),
  CONSTRAINT `fk_player_catalog`
    FOREIGN KEY (`catalog_id`) REFERENCES `Catalog` (`catalog_id`)
);

CREATE TABLE `Relationship` (
  `relationship_id` INT    NOT NULL AUTO_INCREMENT,
  `x_id`            INT    NOT NULL,
  `y_id`            INT    NOT NULL,
  `common`          INT    NULL,
  `relation`        DOUBLE NULL,
  `strength`        DOUBLE NULL,
  PRIMARY KEY (`relationship_id`),
  UNIQUE KEY `uq_relationship_pair` (`x_id`, `y_id`),
  CONSTRAINT `fk_relationship_x`
    FOREIGN KEY (`x_id`) REFERENCES `Chart` (`global_chart_id`),
  CONSTRAINT `fk_relationship_y`
    FOREIGN KEY (`y_id`) REFERENCES `Chart` (`global_chart_id`)
);

CREATE TABLE `Score` (
  `score_id`             INT         NOT NULL AUTO_INCREMENT,
  `catalog_id`           INT         NOT NULL,
  `global_chart_id`      INT         NOT NULL,
  `performance_id`       INT         NOT NULL,
  `plays`                INT         NULL,
  `last_played`          DATETIME    NULL,
  `clear`                VARCHAR(20) NULL,
  `score`                DOUBLE      NULL,
  `prediction`           DOUBLE      NULL,
  `prediction_calc_time` DATETIME    NULL,
  PRIMARY KEY (`score_id`),
  UNIQUE KEY `uq_score_player_chart` (`performance_id`, `global_chart_id`),
  KEY `idx_score_lookup` (`catalog_id`, `performance_id`),
  CONSTRAINT `fk_score_catalog`
    FOREIGN KEY (`catalog_id`) REFERENCES `Catalog` (`catalog_id`),
  CONSTRAINT `fk_score_chart`
    FOREIGN KEY (`global_chart_id`) REFERENCES `Chart` (`global_chart_id`),
  CONSTRAINT `fk_score_player`
    FOREIGN KEY (`performance_id`) REFERENCES `Player` (`performance_id`)
);
