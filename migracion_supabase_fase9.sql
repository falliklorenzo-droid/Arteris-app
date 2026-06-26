-- ════════════════════════════════════════════════════════════════════════════
-- migracion_supabase_fase9.sql
-- FIX 5 — Endurecimiento de RLS para datos de salud (Ley 25.326)
-- ════════════════════════════════════════════════════════════════════════════
--
-- CONTEXTO
--   Hoy la app y el job se conectan con la ANON key. Las tablas con RLS activo
--   tienen políticas permisivas USING(true) para el rol `anon`, así que en la
--   práctica TODA la base es accesible con la anon key (que es pública). Tres
--   tablas (historial_procedimientos, eventos_adversos, alertas) ni siquiera
--   tienen RLS activado.
--
-- QUÉ HACE ESTA MIGRACIÓN
--   1) Activa RLS en las 3 tablas que lo tienen desactivado.
--   2) Elimina las políticas permisivas que habilitan el acceso anónimo.
--   Con RLS activo y sin políticas, los roles `anon` y `authenticated` quedan
--   DENEGADOS en todas las tablas. El rol `service_role` IGNORA RLS por diseño,
--   así que la app y el job siguen funcionando sin cambios de código.
--
-- ⚠️  ORDEN DE EJECUCIÓN — MUY IMPORTANTE
--   Ejecutar este SQL SOLO DESPUÉS de haber migrado la app Y el job a la
--   service_role key (Railway env, GitHub Secret y secrets.toml local) y de
--   haber verificado que la app levanta y opera con normalidad.
--   Si se ejecuta mientras la app sigue con la anon key, se corta la producción.
-- ════════════════════════════════════════════════════════════════════════════

-- 1) Activar RLS en las tablas que hoy lo tienen desactivado
ALTER TABLE public.historial_procedimientos ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.eventos_adversos         ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.alertas                  ENABLE ROW LEVEL SECURITY;

-- 2) Quitar las políticas permisivas que habilitan acceso anónimo (USING(true))
DROP POLICY IF EXISTS "Acceso total pacientes"       ON public.pacientes;
DROP POLICY IF EXISTS "Acceso total mediciones"      ON public.mediciones;
DROP POLICY IF EXISTS "Medicos ven su propio perfil" ON public.medicos;
DROP POLICY IF EXISTS "Acceso notas"                 ON public.notas_medico;

-- Resultado final: RLS activo en TODAS las tablas y sin políticas para anon.
-- → anon / authenticated: denegados.
-- → service_role (servidor): acceso completo (ignora RLS).

-- ════════════════════════════════════════════════════════════════════════════
-- ROLLBACK (volver al estado anterior si algo falla)
-- ════════════════════════════════════════════════════════════════════════════
-- CREATE POLICY "Acceso total pacientes"  ON public.pacientes
--     FOR ALL TO anon, authenticated, service_role USING (true) WITH CHECK (true);
-- CREATE POLICY "Acceso total mediciones" ON public.mediciones
--     FOR ALL TO anon, authenticated, service_role USING (true) WITH CHECK (true);
-- CREATE POLICY "Medicos ven su propio perfil" ON public.medicos
--     FOR ALL TO public USING (true) WITH CHECK (true);
-- CREATE POLICY "Acceso notas" ON public.notas_medico
--     FOR ALL TO public USING (true) WITH CHECK (true);
-- ALTER TABLE public.historial_procedimientos DISABLE ROW LEVEL SECURITY;
-- ALTER TABLE public.eventos_adversos         DISABLE ROW LEVEL SECURITY;
-- ALTER TABLE public.alertas                  DISABLE ROW LEVEL SECURITY;
