-- Jalankan di Supabase > SQL Editor. Ganti EMAIL_GOOGLE_TOKO dengan email Google toko.
-- Setelah ini hanya akun Google tersebut yang bisa membaca/menulis data.
drop policy if exists "akses toko" on items;
drop policy if exists "akses toko" on transactions;
create policy "hanya pemilik" on items for all to authenticated
  using ((auth.jwt() ->> 'email') = 'EMAIL_GOOGLE_TOKO')
  with check ((auth.jwt() ->> 'email') = 'EMAIL_GOOGLE_TOKO');
create policy "hanya pemilik" on transactions for all to authenticated
  using ((auth.jwt() ->> 'email') = 'EMAIL_GOOGLE_TOKO')
  with check ((auth.jwt() ->> 'email') = 'EMAIL_GOOGLE_TOKO');
