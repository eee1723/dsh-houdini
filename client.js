// dsh-houdini client half — registers the "Houdini Trace" conversation view
// (parallel to the built-in "chat" and "trajectory" views). It reads the
// runtime verb ledger that the bridge writes into each houdini_* tool result
// and renders it as a scannable list: verb, status, inputs, outputs, timing.
//
// Hand-written CJS factory matching the dsh client module system (no bundler):
// the bundle only REGISTERS its factory here; the body runs at materialization.
window.__ModuleLoader__.load({
  id: "dsh-houdini",
  factory: function (require) {
    var React = require("react");

    var rootStyle = {
      display: "flex",
      flexDirection: "column",
      gap: "12px",
      padding: "16px",
      height: "100%",
      overflow: "auto",
      boxSizing: "border-box",
      color: "var(--dsw-alias-label-primary, #e8e8e8)",
    };
    var emptyStyle = {
      color: "var(--dsw-alias-label-secondary, #999)",
      padding: "32px",
      textAlign: "center",
    };
    var callStyle = {
      border: "1px solid var(--dsw-alias-border-l2, #333)",
      borderRadius: "8px",
      padding: "10px 12px",
      background: "var(--dsw-alias-bg-layer-2, #1b1b1b)",
    };
    var headStyle = { fontWeight: "600", marginBottom: "6px", fontSize: "12px" };
    var preStyle = {
      margin: 0,
      fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
      fontSize: "11px",
      lineHeight: 1.5,
      whiteSpace: "pre-wrap",
      wordBreak: "break-word",
    };

    function apply(ctx) {
      var slots = ctx.get("slots");
      if (slots === undefined) return;

      slots.inject("conversation.view", function () {
        return slots.register(
          { name: "conversation.view", id: "houdinitrace", order: 5, label: "Houdini Trace" },
          function HoudiniTraceView(props) {
            var nodes = props.useSession(function (s) { return s.nodes; });
            var entries = [];
            var list = nodes || [];
            for (var i = 0; i < list.length; i++) {
              var node = list[i];
              if (node.kind !== "tool-result") continue;
              var call = node.call;
              var name = call ? call.name : null;
              if (typeof name !== "string" || name.indexOf("houdini") !== 0) continue;
              var text = "";
              var blocks = node.content || [];
              for (var j = 0; j < blocks.length; j++) {
                var b = blocks[j];
                if (b && b.type === "text" && typeof b.text === "string") text += b.text + "\n";
              }
              var idx = text.indexOf("verbs (");
              if (idx === -1) continue;
              entries.push({ key: String(node.seq), name: name, verbText: text.slice(idx) });
            }

            if (entries.length === 0) {
              return React.createElement("div", { style: emptyStyle }, "No Houdini verb calls recorded yet.");
            }
            var cards = entries.map(function (e) {
              return React.createElement(
                "div",
                { style: callStyle, key: e.key },
                React.createElement("div", { style: headStyle }, e.name),
                React.createElement("pre", { style: preStyle }, e.verbText)
              );
            });
            return React.createElement("div", { style: rootStyle }, cards);
          }
        );
      });
    }

    return { apply: apply };
  },
});
