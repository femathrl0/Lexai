// Espelha contratos/eventos.py. Mudança aqui exige mudança no contrato (PR próprio).
export type Evento =
  | { tipo: "status"; etapa: string; posicao_fila?: number | null }
  | { tipo: "frase"; ordem: number; texto: string; trecho_id: string; trecho_texto: string; fonte: string }
  | { tipo: "aviso"; categoria: string; texto: string }
  | { tipo: "concluido"; versoes: Record<string, unknown> }
  | { tipo: "erro"; mensagem: string; o_que_fazer: string };
