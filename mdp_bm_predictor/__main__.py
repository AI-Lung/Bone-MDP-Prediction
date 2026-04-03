from .gui import PredictorGUI


def main() -> int:
    app = PredictorGUI()
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
