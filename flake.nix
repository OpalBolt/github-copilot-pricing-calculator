{
  description = "GitHub Copilot token cost calculator";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        python = pkgs.python312;
        pythonWithJinja2 = python.withPackages (ps: with ps; [ jinja2 ]);

        # Resolve the project root at runtime from the caller's working directory
        # so that fetch_pricing.py can write pricing.json and generate_html.py can write index.html.
        fetchScript = pkgs.writeShellScript "fetch-pricing" ''
          set -euo pipefail
          exec ${python}/bin/python "$(git rev-parse --show-toplevel 2>/dev/null || pwd)/fetch_pricing.py" "$@"
        '';

        buildScript = pkgs.writeShellScript "build" ''
          set -euo pipefail
          exec ${pythonWithJinja2}/bin/python "$(git rev-parse --show-toplevel 2>/dev/null || pwd)/generate_html.py" "$@"
        '';

        serveScript = pkgs.writeShellScript "serve-calculator" ''
          set -euo pipefail
          ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
          echo "Serving at http://localhost:8080 (root: $ROOT)"
          exec ${python}/bin/python -m http.server 8080 --directory "$ROOT"
        '';
      in
      {
        # `nix develop` — shell with Python + jinja2; use generate_html.py or fetch_pricing.py directly
        devShells.default = pkgs.mkShell {
          name = "token-calculator";

          packages = [
            pythonWithJinja2
            pkgs.ruff
          ];

          shellHook = ''
            echo ""
            echo "  GitHub Copilot · token cost calculator"
            echo ""
            echo "  Build (fetch pricing + generate HTML):"
            echo "    python generate_html.py"
            echo "    python generate_html.py --no-fetch   # use existing pricing.json"
            echo ""
            echo "  Fetch pricing data only:"
            echo "    python fetch_pricing.py"
            echo ""
            echo "  Serve the site locally:"
            echo "    python -m http.server 8080"
            echo "    open http://localhost:8080"
            echo ""
          '';
        };

        # `nix run` — build (fetch + generate) and serve on :8080
        apps.default = {
          type = "app";
          program = "${buildScript}";
        };

        # `nix run .#fetch` — fetch latest pricing into pricing.json
        apps.fetch = {
          type = "app";
          program = "${fetchScript}";
        };

        # `nix run .#build` — fetch + generate HTML
        apps.build = {
          type = "app";
          program = "${buildScript}";
        };

        # `nix run .#serve` — serve on :8080
        apps.serve = {
          type = "app";
          program = "${serveScript}";
        };
      }
    );
}
