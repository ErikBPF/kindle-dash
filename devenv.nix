{pkgs, ...}: {
  # Python + Pillow/requests for the renderer, ruff for fmt/lint, compose to run
  # the container locally. dejavu fonts are wired into the env so `preview` and
  # `serve` work outside the container too.
  packages = [
    (pkgs.python3.withPackages (ps: with ps; [pillow requests]))
    pkgs.ruff
    pkgs.docker-compose
  ];

  env.DASH_FONT_DIR = "${pkgs.dejavu_fonts}/share/fonts/truetype";
  env.DASH_STATE_DIR = "/tmp/kindle-dash-state";

  # `serve` runs the real server on :8080; `preview` renders one PNG to ./preview.png.
  scripts.serve.exec = "cd renderer && python app.py";
  scripts.preview.exec = ''
    cd renderer && python -c "import app; open('../preview.png','wb').write(app.render()); print('wrote preview.png (' + str(app.KINDLE_W) + 'x' + str(app.KINDLE_H) + ')')"
  '';
  scripts.fmt.exec = "ruff format renderer/app.py";
  scripts.lint.exec = "ruff check renderer/app.py";

  enterShell = ''
    mkdir -p "$DASH_STATE_DIR"
    echo "kindle-dash devenv ready — python $(python --version 2>&1 | cut -d' ' -f2)"
    echo "scripts: serve | preview | fmt | lint"
  '';
}
