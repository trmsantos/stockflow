"""Mais um código de erro: o fornecedor do modelo pode estar **ocupado**.

Só `choices`, logo a base de dados não muda — o `AlterField` de um `choices` não
gera DDL nenhum em PostgreSQL, porque a validação vive no Django e não numa
restrição da coluna. A migração existe à mesma para o `makemigrations --check`
do CI ficar limpo e para a lista fechada do enum ter uma data no histórico.

Porque é que o código nasceu: a ADR 0027 d9 pôs `max_retries=0` com o argumento
de que "nenhuma recusa melhora com o tempo". Um 503 "high demand" do nível
gratuito da Gemini melhora — e a frase que a pessoa lê não pode ser a mesma de
uma recusa definitiva (emenda à ADR 0027, 2026-10-16).
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('agents', '0002_conversation_chatmessage'),
    ]

    operations = [
        migrations.AlterField(
            model_name='chatmessage',
            name='error_code',
            field=models.CharField(blank=True, choices=[('teto_de_iteracoes', 'o modelo chamou tools demasiadas vezes'), ('teto_de_custo', 'o orçamento diário do estabelecimento esgotou-se'), ('tempo_esgotado', 'o modelo não respondeu a tempo'), ('resposta_invalida', 'a resposta do modelo não se lê'), ('erro_do_modelo', 'o fornecedor do modelo recusou a chamada'), ('modelo_ocupado', 'o fornecedor está sobrecarregado'), ('pertenca_revogada', 'quem perguntou já não pertence ao estabelecimento')], default='', editable=False, max_length=40, verbose_name='código do erro'),
        ),
    ]
