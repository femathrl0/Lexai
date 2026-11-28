from worker.armazenamento import arquivo_local


def test_arquivo_local_sem_opt_in_e_apagado(tmp_path):
    f = tmp_path / "a.pdf"
    f.write_bytes(b"%PDF")
    with arquivo_local(str(f), guardar=False) as c:
        assert c == str(f)
    assert not f.exists()


def test_arquivo_local_com_opt_in_fica(tmp_path):
    f = tmp_path / "a.pdf"
    f.write_bytes(b"%PDF")
    with arquivo_local(str(f), guardar=True):
        pass
    assert f.exists()
