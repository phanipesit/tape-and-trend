const boldify = (s) => s.split("**").map((part, i) => (i % 2 ? <b key={i} className="text-txt">{part}</b> : part));

export default function Md({ text }) {
  return text.split("\n").map((ln, i) => {
    if (ln.startsWith("## ")) return <h4 key={i} className="font-semibold text-brass mt-3 mb-1">{ln.slice(3)}</h4>;
    if (ln.startsWith("- ")) return <p key={i} className="text-mut pl-3 py-0.5">• {boldify(ln.slice(2))}</p>;
    if (ln.startsWith("*") && ln.endsWith("*") && !ln.startsWith("**")) return <p key={i} className="text-dim text-xs mt-2">{ln.replaceAll("*", "")}</p>;
    if (!ln.trim()) return null;
    return <p key={i} className="text-mut py-0.5">{boldify(ln)}</p>;
  });
}
