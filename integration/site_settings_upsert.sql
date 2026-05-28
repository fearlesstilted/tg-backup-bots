-- Upsert ShmaliShop site_settings to point at the backup bots.
-- Run in Supabase → SQL editor. Idempotent: re-run after rotating bot handles.
--
-- Schema reference (Supabase migration 20260207003513):
--   site_settings(id uuid PK, key text NOT NULL UNIQUE, value text NOT NULL,
--                 updated_at timestamptz NOT NULL DEFAULT now())
-- Read by src/hooks/useSiteSettings.ts (cached in-memory after first fetch).
-- RLS: INSERT/UPDATE/DELETE require has_role(auth.uid(), 'admin'). Run this
-- from the Supabase SQL editor while logged in as a project owner/admin, or
-- bypass RLS with the service-role key.
--
-- If you change either bot handle in @BotFather, edit the six VALUES below
-- and re-run. Bot side accepts these ?start=… segments out of the box.

INSERT INTO site_settings (key, value) VALUES
  -- Reviews bot (public — anyone can use)
  ('reviews_tg_url_ru', 'https://t.me/reviewsegment_bot?start=ru_reviews'),
  ('reviews_tg_url_en', 'https://t.me/reviewsegment_bot?start=foreign_reviews'),
  ('reviews_tg_url_de', 'https://t.me/reviewsegment_bot?start=foreign_reviews'),

  -- Private bot (VIP — button shown only when hasPaidOrders is true)
  ('private_tg_url_ru', 'https://t.me/privatesegment_bot?start=ru_private'),
  ('private_tg_url_en', 'https://t.me/privatesegment_bot?start=foreign_private'),
  ('private_tg_url_de', 'https://t.me/privatesegment_bot?start=foreign_private')
ON CONFLICT (key) DO UPDATE
  SET value = EXCLUDED.value,
      updated_at = now();

-- Verify
SELECT key, value
FROM site_settings
WHERE key IN (
  'reviews_tg_url_ru', 'reviews_tg_url_en', 'reviews_tg_url_de',
  'private_tg_url_ru', 'private_tg_url_en', 'private_tg_url_de'
)
ORDER BY key;
