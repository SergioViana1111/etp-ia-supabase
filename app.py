def mover_access_token_do_hash_para_query():
    """Converte #access_token=... para ?access_token=... e recarrega IMEDIATAMENTE."""
    
    # O script usa window.location.replace para modificar a URL sem adicionar ao histórico
    # O setTimeout é uma segurança para dar tempo do Streamlit carregar o componente, embora
    # normalmente não seja necessário.
    components.html(
        """
        <script>
        (function() {
            console.log('Verificando hash para Supabase token...');
            if (window.location.hash && window.location.hash.includes("access_token=")) {
                const params = new URLSearchParams(window.location.hash.substring(1));
                const access = params.get("access_token");
                const url = new URL(window.location.href.split('#')[0]);
                
                if (access) {
                    console.log('Token encontrado. Redirecionando...');
                    url.searchParams.set("access_token", access);
                    // Importante: remove o hash e adiciona o token na query
                    window.location.replace(url.toString()); 
                }
            }
        })();
        </script>
        """,
        height=0, # Altura 0 para ser invisível
    )
