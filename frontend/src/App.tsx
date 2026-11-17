import { useState } from "react";
import type { Evento } from "./eventos";

const AVISO =
  "O Lexai explica o que o documento diz; não substitui advogado, Defensoria Pública ou o setor de atermação.";

export function App() {
  const [arquivo, setArquivo] = useState<File | null>(null);
  const [guardar, setGuardar] = useState(false);
  const [eventos, setEventos] = useState<Evento[]>([]);
  const [enviando, setEnviando] = useState(false);

  async function enviar(e: React.FormEvent) {
    e.preventDefault();
    if (!arquivo) return;
    setEnviando(true);
    setEventos([]);
    const corpo = new FormData();
    corpo.append("arquivo", arquivo);
    corpo.append("guardar", String(guardar));
    const r = await fetch("/api/tarefas/documentos", { method: "POST", body: corpo });
    const { tarefa_id } = await r.json();
    // TODO (Eng. de software): reconectar informando a última frase recebida.
    const fonte = new EventSource(`/api/tarefas/${tarefa_id}/eventos`);
    fonte.onmessage = (m) => {
      const ev = JSON.parse(m.data) as Evento;
      setEventos((xs) => [...xs, ev]);
      if (ev.tipo === "concluido" || ev.tipo === "erro") {
        fonte.close();
        setEnviando(false);
      }
    };
  }

  const ultimaEtapa = [...eventos].reverse().find((e) => e.tipo === "status");

  return (
    <main>
      <header>
        <h1>Lexai</h1>
        <p role="note" className="aviso-fixo">{AVISO}</p>
      </header>

      <form onSubmit={enviar} aria-label="Enviar documento do processo">
        <label htmlFor="arquivo">Documento do processo (PDF ou foto)</label>
        <input id="arquivo" type="file" accept="application/pdf,image/*"
          onChange={(e) => setArquivo(e.target.files?.[0] ?? null)} />
        <label className="consentimento">
          <input type="checkbox" checked={guardar} onChange={(e) => setGuardar(e.target.checked)} />
          Quero guardar este documento na minha conta (criptografado, com prazo de exclusão). Sem marcar, ele é
          processado e descartado.
        </label>
        <button type="submit" disabled={!arquivo || enviando}>Explicar documento</button>
      </form>

      <section aria-live="polite" aria-busy={enviando}>
        {ultimaEtapa?.tipo === "status" && enviando && <p>Etapa: {ultimaEtapa.etapa}</p>}
        {eventos.map((ev, i) =>
          ev.tipo === "frase" ? (
            <div key={i} className="frase">
              <p>{ev.texto}</p>
              <blockquote cite={ev.fonte}>{ev.trecho_texto} <cite>{ev.fonte}</cite></blockquote>
            </div>
          ) : ev.tipo === "aviso" ? (
            <p key={i} className="aviso" role="status">{ev.texto}</p>
          ) : ev.tipo === "erro" ? (
            <p key={i} className="erro" role="alert">{ev.mensagem} {ev.o_que_fazer}</p>
          ) : null,
        )}
      </section>
    </main>
  );
}
