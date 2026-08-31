from processor import process_file


def main():
    test_bytes = b"supplier,product,price\nAcme,Widget,9.99"
    results = process_file(test_bytes)
    assert isinstance(results, list)
    assert len(results) > 0
    assert isinstance(results[0], dict)
    assert "title" in results[0]
    assert "status" in results[0]
    assert "details" in results[0]
    assert "due_date" in results[0]
    print("Demo passed. First record:", results[0])


if __name__ == "__main__":
    main()
