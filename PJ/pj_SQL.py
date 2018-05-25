"""Jednostavni SQL parser, samo za nizove CREATE i SELECT naredbi.

Ovaj fragment SQLa je zapravo regularan -- nigdje nema ugnježđivanja!
Semantički analizator u obliku name resolvera:
    provjerava jesu li svi selektirani stupci prisutni, te broji pristupe.
Na dnu je lista ideja za dalji razvoj."""


from pj import *
import pprint


class SQL(enum.Enum):
    class IME(Token): pass
    class BROJ(Token): pass
    SELECT, FROM, CREATE, TABLE = 'SELECT', 'FROM', 'CREATE', 'TABLE'
    OTVORENA, ZATVORENA, ZVJEZDICA, ZAREZ, TOČKAZAREZ = '()*,;'
    KOMENTAR = '--'


def sql_lex(kôd):
    lex = Tokenizer(kôd)
    for znak in iter(lex.čitaj, ''):
        if znak.isspace(): lex.token(E.PRAZNO)
        elif znak.isdigit():
            lex.zvijezda(str.isdigit)
            yield lex.token(SQL.BROJ)
        elif znak == '-':
            lex.pročitaj('-')
            lex.zvijezda(lambda znak: znak != '\n')
            lex.pročitaj('\n')
            lex.token(SQL.KOMENTAR)
        elif znak.isalpha():
            lex.zvijezda(str.isalnum)
            yield lex.token(ključna_riječ(SQL, lex.sadržaj, False) or SQL.IME)
        else: yield lex.token(operator(SQL, znak) or lex.greška())


### Beskontekstna gramatika:
# start -> naredba | naredba start
# naredba -> ( select | create ) TOČKAZAREZ
# select -> SELECT ( ZVJEZDICA | stupci ) FROM IME
# stupci -> IME ZAREZ stupci | IME
# create -> CREATE TABLE IME OTVORENA spec_stupci ZATVORENA
# spec_stupci -> spec_stupac ZAREZ spec_stupci | spec_stupac
# spec_stupac -> IME IME | IME IME OTVORENA BROJ ZATVORENA

### Apstraktna sintaksna stabla:
# Skripta: naredbe - niz SQL naredbi, svaka završava znakom ';'
# Create: tablica, specifikacije - CREATE TABLE naredba
# Select: tablica, stupci - SELECT naredba; stupci == nenavedeno za SELECT *
# Stupac: ime, tip, veličina - specifikacija stupca u tablici (za Create)


class SQLParser(Parser):
    def select(self):
        if self >> SQL.ZVJEZDICA: stupci = nenavedeno
        elif self >> SQL.IME:
            sve = False
            stupci = [self.zadnji]
            while self >> SQL.ZAREZ: stupci.append(self.pročitaj(SQL.IME))
        else: self.greška()
        self.pročitaj(SQL.FROM)        
        return Select(self.pročitaj(SQL.IME), stupci)

    def spec_stupac(self):
        ime, tip = self.pročitaj(SQL.IME), self.pročitaj(SQL.IME)
        if self >> SQL.OTVORENA:
            veličina = self.pročitaj(SQL.BROJ)
            self.pročitaj(SQL.ZATVORENA)
        else: veličina = nenavedeno
        return Stupac(ime, tip, veličina)

    def create(self):
        self.pročitaj(SQL.TABLE)
        tablica = self.pročitaj(SQL.IME)
        self.pročitaj(SQL.OTVORENA)
        stupci = [self.spec_stupac()]
        while self >> SQL.ZAREZ: stupci.append(self.spec_stupac())
        self.pročitaj(SQL.ZATVORENA)
        return Create(tablica, stupci)

    def naredba(self):
        if self >> SQL.SELECT: rezultat = self.select()
        elif self >> SQL.CREATE: rezultat = self.create()
        else: self.greška()
        self.pročitaj(SQL.TOČKAZAREZ)
        return rezultat

    def start(self):
        naredbe = [self.naredba()]
        while not self >> E.KRAJ: naredbe.append(self.naredba())
        return Skripta(naredbe)


class Skripta(AST('naredbe')):
    """Niz SQL naredbi, svaka završava znakom ';'."""
    def razriješi(self):
        imena = {}
        for naredba in self.naredbe: naredba.razriješi(imena)
        return imena

class Create(AST('tablica specifikacije')):
    """CREATE TABLE naredba."""
    def razriješi(self, imena):
        tb = imena[self.tablica.sadržaj] = {}
        for stupac in self.specifikacije:
            tb[stupac.ime.sadržaj] = StupacLog(stupac)
        
class Select(AST('tablica stupci')):
    """SELECT naredba."""
    def razriješi(self, imena):
        tn = self.tablica.sadržaj
        if tn not in imena: self.tablica.nedeklaracija('nema tablice')
        tb = imena[tn]
        if self.stupci is nenavedeno:
            for log in tb.values(): log.pristup += 1
        else:
            for st in self.stupci:
                sn = st.sadržaj
                if sn not in tb:
                    st.nedeklaracija('stupca nema u tablici {}'.format(tn))
                tb[sn].pristup += 1

class Stupac(AST('ime tip veličina')): """Specifikacija stupca u tablici."""


class StupacLog(types.SimpleNamespace):
    """Zapis o tome koliko je puta pristupljeno određenom stupcu."""
    def __init__(self, specifikacija):
        self.tip = specifikacija.tip.sadržaj
        vel = specifikacija.veličina
        if vel: self.veličina = int(vel.sadržaj)
        self.pristup = 0


if __name__ == '__main__':
    skripta = SQLParser.parsiraj(sql_lex('''\
            CREATE TABLE Persons
            (
                PersonID int,
                Name varchar(255),  -- neki stupci imaju zadanu veličinu
                Birthday date,      -- a neki nemaju...
                Married bool,
                City varchar(9)     -- zadnji nema zarez!
            );  -- Sada krenimo nešto selektirati
            SELECT Name, City FROM Persons;
            SELECT * FROM Persons;
            CREATE TABLE Trivial (ID void(0));  -- još jedna tablica
            SELECT*FROM Trivial;  -- između simbola i riječi ne mora ići razmak
            SELECT Name, Married FROM Persons;
            SELECT Name from Persons;
    '''))
    pprint.pprint(skripta.razriješi())

# ideje za dalji razvoj:
    # StupacLog.pristup umjesto samog broja može biti lista brojeva linija \
    # skripte u kojima počinju SELECT naredbe koje pristupaju pojedinom stupcu
    # za_indeks(skripta): lista natprosječno dohvaćivanih tablica/stupaca
    # optimizacija: brisanje iz CREATE stupaca kojima nismo uopće pristupili
    # implementirati INSERT INTO, da možemo doista nešto i raditi s podacima
    # povratni tip za SELECT (npr. (varchar(255), bool) za ovaj zadnji)
    # interaktivni način rada (online - naredbu po naredbu analizirati)
