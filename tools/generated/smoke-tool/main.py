from pathlib import Path


def main():
    output = Path('output')
    output.mkdir(exist_ok=True)
    report = output / 'report.md'
    report.write_text('# Tool Report\n\nTool executed.\n', encoding='utf-8')
    print(report)


if __name__ == '__main__':
    main()
