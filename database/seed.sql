-- Seed forex pairs and metals

INSERT INTO symbols (symbol, name, category, base_currency, quote_currency, pip_size, sort_order) VALUES
-- Majors
('EURUSD', 'Euro / US Dollar', 'major', 'EUR', 'USD', 0.0001, 1),
('GBPUSD', 'British Pound / US Dollar', 'major', 'GBP', 'USD', 0.0001, 2),
('USDJPY', 'US Dollar / Japanese Yen', 'major', 'USD', 'JPY', 0.01, 3),
('USDCHF', 'US Dollar / Swiss Franc', 'major', 'USD', 'CHF', 0.0001, 4),
('AUDUSD', 'Australian Dollar / US Dollar', 'major', 'AUD', 'USD', 0.0001, 5),
('USDCAD', 'US Dollar / Canadian Dollar', 'major', 'USD', 'CAD', 0.0001, 6),
('NZDUSD', 'New Zealand Dollar / US Dollar', 'major', 'NZD', 'USD', 0.0001, 7),
-- Minors
('EURGBP', 'Euro / British Pound', 'minor', 'EUR', 'GBP', 0.0001, 10),
('EURJPY', 'Euro / Japanese Yen', 'minor', 'EUR', 'JPY', 0.01, 11),
('GBPJPY', 'British Pound / Japanese Yen', 'minor', 'GBP', 'JPY', 0.01, 12),
('EURCHF', 'Euro / Swiss Franc', 'minor', 'EUR', 'CHF', 0.0001, 13),
('EURAUD', 'Euro / Australian Dollar', 'minor', 'EUR', 'AUD', 0.0001, 14),
('EURCAD', 'Euro / Canadian Dollar', 'minor', 'EUR', 'CAD', 0.0001, 15),
('EURNZD', 'Euro / New Zealand Dollar', 'minor', 'EUR', 'NZD', 0.0001, 16),
('GBPCHF', 'British Pound / Swiss Franc', 'minor', 'GBP', 'CHF', 0.0001, 17),
('GBPAUD', 'British Pound / Australian Dollar', 'minor', 'GBP', 'AUD', 0.0001, 18),
('GBPCAD', 'British Pound / Canadian Dollar', 'minor', 'GBP', 'CAD', 0.0001, 19),
('GBPNZD', 'British Pound / New Zealand Dollar', 'minor', 'GBP', 'NZD', 0.0001, 20),
('AUDJPY', 'Australian Dollar / Japanese Yen', 'minor', 'AUD', 'JPY', 0.01, 21),
('AUDCHF', 'Australian Dollar / Swiss Franc', 'minor', 'AUD', 'CHF', 0.0001, 22),
('AUDCAD', 'Australian Dollar / Canadian Dollar', 'minor', 'AUD', 'CAD', 0.0001, 23),
('AUDNZD', 'Australian Dollar / New Zealand Dollar', 'minor', 'AUD', 'NZD', 0.0001, 24),
('CADJPY', 'Canadian Dollar / Japanese Yen', 'minor', 'CAD', 'JPY', 0.01, 25),
('CHFJPY', 'Swiss Franc / Japanese Yen', 'minor', 'CHF', 'JPY', 0.01, 26),
('NZDJPY', 'New Zealand Dollar / Japanese Yen', 'minor', 'NZD', 'JPY', 0.01, 27),
('NZDCAD', 'New Zealand Dollar / Canadian Dollar', 'minor', 'NZD', 'CAD', 0.0001, 28),
-- Metals
('XAUUSD', 'Gold / US Dollar', 'metal', 'XAU', 'USD', 0.01, 50),
('XAGUSD', 'Silver / US Dollar', 'metal', 'XAG', 'USD', 0.001, 51),
-- Commodities
('USOIL', 'WTI Crude Oil', 'commodity', 'OIL', 'USD', 0.01, 60),
('UKOIL', 'Brent Crude Oil', 'commodity', 'OIL', 'USD', 0.01, 61);
