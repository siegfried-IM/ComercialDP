# -*- coding: utf-8 -*-
"""Valida las expresiones de unidades (total mercado y potencial no capturado)
para un mercado en la ventana TRIM del período actual, comparando contra la
medida maestra 'TRIM Act.' [NXBSm]. Solo lectura + selecciones temporales."""
from qlik_client import Qix
import config as C

MERCADO = "Acemuk"
S = 2  # TRIM: max-2 .. max

# total mercado (todos los labs), ventana TRIM
U_TOT = ("sum({<Flag_Rollback={0},MesesRollBack=,DescMercadoTipo=,"
         "[AñoMes_Num]={\">=$(=max(AñoMes_Num)-%d)<=$(=max(AñoMes_Num)-0)\"}>}MensualUnidades)" % S)
# unidades Siegfried, misma ventana
U_SIE = ("sum({<DescripcionLaboratorioIMS={'SIEGFRIED'},Flag_Rollback={0},MesesRollBack=,DescMercadoTipo=,"
         "[AñoMes_Num]={\">=$(=max(AñoMes_Num)-%d)<=$(=max(AñoMes_Num)-0)\"}>}MensualUnidades)" % S)
# ventana como set-modifier reutilizable
WSET = ("{<Flag_Rollback={0},MesesRollBack=,DescMercadoTipo=,"
        "[AñoMes_Num]={\">=$(=max(AñoMes_Num)-%d)<=$(=max(AñoMes_Num)-0)\"}>}" % S)
WSET_SIE = ("{<DescripcionLaboratorioIMS={'SIEGFRIED'},Flag_Rollback={0},MesesRollBack=,DescMercadoTipo=,"
            "[AñoMes_Num]={\">=$(=max(AñoMes_Num)-%d)<=$(=max(AñoMes_Num)-0)\"}>}" % S)
# potencial NO capturado: Aggr por CPA -> si la farmacia no tiene SIE, sumar unidades del mercado
U_GAP = ("sum(aggr(if(sum(%s MensualUnidades)=0, sum(%s MensualUnidades), 0), CPA))" % (WSET_SIE, WSET))
U_PRESENT = ("sum(aggr(if(sum(%s MensualUnidades)>0, sum(%s MensualUnidades), 0), CPA))" % (WSET_SIE, WSET))
REF_NXBSm = "sum({<Flag_Rollback={0},MesesRollBack=,DescMercadoTipo=,[AñoMes_Num]={\">=$(=max(AñoMes_Num)-2)<=$(=max(AñoMes_Num)-0)\"}>}MensualUnidades)"


def val(q, doc, e):
    r = q.evaluate(doc, "=" + e)
    try:
        return float(str(r).replace(".", "").replace(",", ".")) if "," in str(r) else float(r)
    except Exception:
        return r


def main():
    q = Qix(); doc = q.open_doc(); q.clear_all(doc)
    q.select_text(doc, "TipoMercado", C.TIPO_MERCADO)
    q.select_text(doc, "DescripcionMercado", MERCADO)
    maxp = q.evaluate(doc, "=Max([AñoMes_Num])")
    print(f"Mercado={MERCADO} | maxPeriodo={maxp} | ventana TRIM (S={S})")
    tot = val(q, doc, U_TOT); ref = val(q, doc, REF_NXBSm)
    sie = val(q, doc, U_SIE); gap = val(q, doc, U_GAP); pre = val(q, doc, U_PRESENT)
    print(f"  U_TOT (mercado)      = {tot}")
    print(f"  REF NXBSm 'TRIM Act.'= {ref}  (deberia == U_TOT)")
    print(f"  U_SIE (Siegfried)    = {sie}")
    print(f"  U_GAP (no capturado) = {gap}")
    print(f"  U_PRESENT (con SIE)  = {pre}")
    try:
        print(f"  control GAP+PRESENT  = {gap+pre}  (deberia == U_TOT={tot})")
        print(f"  % no capturado       = {100*gap/tot:.1f}%" if tot else "  s/tot")
    except Exception as e:
        print("  control:", e)
    q.close()


if __name__ == "__main__":
    main()
