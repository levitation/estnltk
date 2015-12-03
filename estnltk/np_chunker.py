# -*- coding: utf-8 -*- 
#
#    An experimental chunker that detects Estonian noun phrases based on 
#   the output of dependency syntactic parser. 
#

from __future__ import unicode_literals, print_function

import re

from .names import *
from .text  import Text

from .mw_verbs.utils import WordTemplate

from .maltparser_support import SYNTAX_LABEL
from .maltparser_support import SYNTAX_HEAD
from .maltparser_support import MaltParser

NP_LABEL = 'np_label'

# =============================================================================
#   The Main Class
# =============================================================================

class NounPhraseChunker:
    ''' An experimental noun phrase chunker for Estonian. Attempts to detect 
        non-overlapping phrases from the text. 
        Uses a hybrid approach:
        *) First, it applies a statistical dependency syntactic parser (Maltparser)
           to obtain dependency relations between words;
        *) Then it builds NP phrases by joining together consecutive words sharing
           a dependency relation: mostly in the direction from left to right, 
           "from a word to its governor in the right";
        *) Lastly, it applies a number of postprocessing rules to augment and
           correct the obtained phrases;
    '''

    maltparser = None

    def __init__( self, maltparser = None, **kwargs):
        if not maltparser:
            # Initialize MaltParser automatically
            self.maltparser = MaltParser()
        elif maltparser and type(maltparser) is MaltParser:
            # Use given MaltParser
            self.maltparser = maltparser
        else:
            raise Exception('Unspecified input argument: MaltParser class')


    def analyze_text( self, text, **kwargs ):
        ''' 
        Analyzes given Text for noun phrase chunks. 
            
        Note that in order to obtain a decent performance, it is advisable to analyse 
        texts at their full extent with this method. Splitting a text into smaller 
        chunks, such as clauses or sentences, and analysing one-small-chunk-at-time 
        may be rather demanding in terms of performance, because a file-based 
        preprocessing is used for obtaining the dependency relations.

        Parameters
        ----------
        text:  estnltk.text.Text
            The input text that should be analysed for noun phrases; 

        textIsParsed: boolean
            If True, the input text has already been parsed for dependency 
            relations, so the parsing step will be skipped;
            (default: False)

        cutPhrases: boolean
            If True, all phrases exceeding the cutMaxThreshold will be 
            cut into single word phrases, consisting only of part-of-speech 
            categories 'S', 'Y', 'H';
            (default: False)

        cutMaxThreshold: int
            Threshold indicating the maximum number of words allowed in a 
            phrase.
            If cutPhrases is set, all phrases exceeding the threshold will be 
            cut into single word phrases, consisting only of part-of-speech 
            categories 'S', 'Y', 'H';
            Automatic analysis of the Balanced Corpus of Estonian suggests 
            that 97% of all NP chunks are likely chunks of length 1-3, thus 
            the default threshold is set to 3;
            (default value: 3)
        
        '''
        # 0) Parse given arguments
        textIsParsed    = False
        cutPhrases      = True
        cutMaxThreshold = 3
        for argName, argVal in kwargs.items():
            if argName == 'textIsParsed':
                textIsParsed = bool(argVal)
            elif argName == 'cutPhrases':
                cutPhrases = bool(argVal)
            elif argName == 'cutMaxThreshold':
                cutMaxThreshold = int(argVal)
            else:
                raise Exception(' Unsupported argument given: '+argName)

        # 1) Analyze text with Maltparser to obtain dependency syntactic relations
        #    (if required)
        if not textIsParsed:
            self.maltparser.parse_text(text, return_conll=False)

        # 2) Process text sentence by sentence
        for sentence in text.divide( layer=WORDS, by=SENTENCES ):
            npLabels = self.find_phrases( sentence, cutPhrases, cutMaxThreshold )
            for i in range(len(sentence)):
                word = sentence[i]
                word[NP_LABEL] = npLabels[i]


    # =============================================================
    #    Utils
    # =============================================================

    _AdvStartingPhrase = WordTemplate(\
        {ROOT:'^(mitte|ei|ilma|väga|umbes|liiga|peaaegu|pisut)$',POSTAG:'[D]'})
    # TODO: tegelikult on yldse kysitav, kas siin midagi peale 'mitte'/'ei' peaks lubama ...

    _punctPos     = WordTemplate( {POSTAG:'[Z]'} )
    _jaNingEgaVoi = WordTemplate({ROOT:'^(ja|ning|ega|v[\u014D\u00F5]i)$',POSTAG:'[DJ]'})
    _k6ige        = WordTemplate({ROOT:'^(k[\u014D\u00F5]ige)$',POSTAG:'[D]'})
    _verbParticle     = WordTemplate({POSTAG:'[A]', ROOT:'^.+(tav|v|nud|tud)$'})
    _verbPastParticle = WordTemplate({POSTAG:'[A]', ROOT:'^.+(nud|tud)$'})
    
    def _getPOS( self, token, onlyFirst = True ):
        ''' Returns POS of the current token.
        '''
        if onlyFirst:
            return token[ANALYSIS][0][POSTAG]
        else:
            return [ a[POSTAG] for a in token[ANALYSIS] ]

    def _getPhrase( self, i, sentence, NPlabels ):
        ''' Fetches the full length phrase from the position i
            based on the existing NP phrase annotations (from 
            NPlabels);
            Returns list of sentence tokens in the phrase, and 
            indices of the phrase;
        ''' 
        phrase  = []
        indices = []
        if 0 <= i and i < len(sentence) and NPlabels[i] == 'B':
            phrase  = [ sentence[i] ]
            indices = [ i ]
            j = i + 1
            while ( j < len(sentence) ):
                if NPlabels[j] in ['B', '']:
                    break
                else:
                    phrase.append( sentence[j] )
                    indices.append( j )
                j += 1
        return phrase, indices

    def _getCaseAgreement(self, token1, token2):
        '''  Detects whether there is a morphological case agreement 
            between two consecutive nominals (token1 and token2), and 
            returns the common case, or None if no agreement exists;
             Applies a special set of rules for detecting agreement on
            the word in genitive followed by the word in ter, es, ab or
            kom.
        '''
        forms1 = set( [a[FORM] for a in token1[ANALYSIS]] )
        forms2 = set( [a[FORM] for a in token2[ANALYSIS]] )
        if len(forms1.intersection(forms2))==0:
            # Kontrollime ka ni-na-ta-ga k22ndeid:
            if 'sg g' in forms1:
                if 'sg ter' in forms2:
                    return 'sg ter'
                elif 'sg es' in forms2:
                    return 'sg es'
                elif 'sg ab' in forms2:
                    return 'sg ab'
                elif 'sg kom' in forms2:
                    return 'sg kom'
            elif 'pl g' in forms1:
                if 'pl ter' in forms2:
                    return 'pl ter'
                elif 'pl es' in forms2:
                    return 'pl es'
                elif 'pl ab' in forms2:
                    return 'pl ab'
                elif 'pl kom' in forms2:
                    return 'pl kom'
            return None
        else:
            return list(forms1.intersection(forms2))[0]


    # =============================================================
    #   Detect NP phrases based on the local dependency relations
    # =============================================================
    
    def find_phrases( self, sentence, cutPhrases, cutMaxThreshold ):
        ''' Detects NP phrases by relying on local dependency relations:
            1) Identifies potential heads of NP phrases;
            2) Identifies consecutive words that can form an NP phrase:
               2.1) potential attribute + potential head;
               2.2) quantity word or phrase + nominal;
            3) Identifies non-consecutive words (word1 __ wordN) that
               potentially form a complete phrase (including the gap
               part);
            4) Applies post-corrections;
        '''
        NPattribPos = [ 'Y', 'S', 'A', 'C', 'G', 'H', 'N', 'O', 'K', 'D', 'P' ]
        NPheadPos   = [ 'S', 'Y', 'H' ]
        NPlabels = [ '' for i in range(len(sentence)) ]
        #
        # 0 Faas: M2rgistame k6ik s6nad, mis v6iksid olla nimis6nafraasi peas6nad, nt:
        #        Kas [venelaste] [ambitsioon] on [siiras] ?
        #        [Raskused] algasid [aastal] 2009 , mil oli [majanduskriis] .
        #        [Põllumaad] on ka , aga [kartulikasvatamisega] on üksjagu [jamamist] .
        #
        for i in range(len(sentence)):
            pos1 = self._getPOS(sentence[i])
            if pos1 in NPheadPos:
                NPlabels[i] = 'B'
            # Lisaks märgistame ka peasõnadena ka üksikud pronoomenid, kuigi 
            # eeldame, et need on peasõnadena vaid üksikutes fraasides;
            elif pos1 == 'P':
                NPlabels[i] = 'B'
        #
        # I Faas: liidame yheks nimis6nafraasiks k6ik k6rvutiseisvad nimis6nafraasi
        #     sobivad s6nad, kui esimene on järgmise vahetu alluv, nt:
        #        [Venemaa otsus] alustada Süürias õhurünnakuid ...
        #        Kas [venelaste ambitsioon] on siiras ?
        #        [Järgmine hoop] tuli 2012-2013 ...
        #        [Eelmise nädala reedel] , [19. septembril] leidsid [kolleegid] ...
        #        
        for i in range(len(sentence)):
            label1  = sentence[i][SYNTAX_LABEL]
            parent1 = sentence[i][SYNTAX_HEAD]
            if i+1 < len(sentence):
                label2  = sentence[i+1][SYNTAX_LABEL]
                parent2 = sentence[i+1][SYNTAX_HEAD]
                pos1 = self._getPOS(sentence[i])
                pos2 = self._getPOS(sentence[i+1])
                if int(parent1) == int(label2) and pos1 in NPattribPos and \
                   pos2 in NPheadPos:
                    if 'K' in pos1 and NPlabels[i] == '':
                        #
                        #   1) erandjuht: 
                        #    K fraasi alguses viitab peaaegu alati mingile jamale, 
                        #    seega katkestame, et vältida selliseid asju nagu:
                        #      ... , mille [kohta Eestiski] piisavalt näiteid .
                        #      ... lähedaste majandussidemete [tõttu Brasiiliaga] .
                        #      ... kultuuri allutamise [vastu rahavõimule] , vaid töötavad
                        # 
                        pass
                    elif 'D' in pos1 and not self._AdvStartingPhrase.matches(sentence[i]):
                        #
                        #   2) erandjuht: 
                        #   Lubame ainult teatud adverbe fraasi algusesse, et vältida selliseid
                        #   juhte nagu nt:
                        #      ... said sõna [ka lapsed] , aga kingitust
                        #      ... kättesaamatuks [nii Nehatu hamburgeriputka] ,
                        #      ... osta [ka hinnaga 1 kr] 
                        #      ... ette [just Los Angelese autonäitusel] ,
                        
                        #   TODO: M6nikord me ikkagi tahame, et D ka sees oleks, nt:
                        #      ... filmis " Tagasi [tulevikku] " ...
                        pass
                    else:
                        if NPlabels[i] == '':
                            NPlabels[i] = 'B'
                        NPlabels[i+1] = 'I'
        #
        # II Faas: Koondame kõrvutipaiknevad ja üksteisega alluvussuhtes olevad arvsõnad/numbrid 
        #     üheks arvudest koosnevaks "NP-fraasiks", nt:
        #       [Sada nelikümmend viis]
        #       [10 405 miljonit]
        #       [kaheksa miljardit]
        #     
        for i in range(len(sentence)):
            label1  = sentence[i][SYNTAX_LABEL]
            parent1 = sentence[i][SYNTAX_HEAD]
            pos1 = self._getPOS(sentence[i])
            if pos1 in ['N', 'O']  and  i+1 < len(sentence):
                label2  = sentence[i+1][SYNTAX_LABEL]
                parent2 = sentence[i+1][SYNTAX_HEAD]
                pos2 = self._getPOS(sentence[i+1])
                if pos2 in ['N', 'O'] and ( int(parent2) == int(label1) or \
                   int(parent1) == int(label2) ):
                    if NPlabels[i] == '':
                        NPlabels[i] = 'B'
                    NPlabels[i+1] = 'I'
        #
        # III Faas: Kleebime otsa NP-fraaside otsa järeltäienditena esinevad numbrilised 
        #     arvud, nt:
        #        Üritus kandis nime [Rahu Missioon 2007.]
        #        Allkirjastas [1. jaanuaril 2004.]
        #        Saabus [uus Peugeot 307] , millest [aastatel 1987-1997] ei osatud unistadagi .
        #        [Perioodil 1997-2001] oli neid rohkem , [vt tabel 1.]
        #
        for i in range(len(sentence)):
            label1  = sentence[i][SYNTAX_LABEL]
            parent1 = sentence[i][SYNTAX_HEAD]
            pos1 = self._getPOS(sentence[i])
            if pos1 in ['N', 'O']  and  i-1 > -1:
                label2  = sentence[i-1][SYNTAX_LABEL]
                parent2 = sentence[i-1][SYNTAX_HEAD]
                if int(parent1) == int(label2) and NPlabels[i-1] != '':
                    NPlabels[i] = 'I'
        #
        # IV Faas: Kleebime arvufraaside(hulgafraaside) otsa järeltäienditena esinevad 
        #     nimisõnad, nt:
        #        Meri laius [100 kilomeetri] pikkusena .
        #        Aasta alguseks oli mahust järel [30-40 protsenti] .
        #        Jah , [kümne aasta] tagusega ei maksa siin üldse võrrelda .
        #        Mees nõudis [10 miljonit dollarit] kahjutasu [10-15 cm] kaugusele .
        #        Eelmisel nädalal võttis endalt elu veel [kaks politseiametnikku] .
        #        Kujutlesin [kaheksa miljonit aastat] vana küpressimetsa [mitukümmend aastat] nooremana .
        #
        for i in range(len(sentence)):
            label1  = sentence[i][SYNTAX_LABEL]
            parent1 = sentence[i][SYNTAX_HEAD]
            pos1 = self._getPOS(sentence[i])
            if pos1 in ['N', 'O']  and  i+1 < len(sentence):
                label2  = sentence[i+1][SYNTAX_LABEL]
                parent2 = sentence[i+1][SYNTAX_HEAD]
                pos2    = self._getPOS(sentence[i+1])
                if int(parent2) == int(label1) and NPlabels[i+1] != '' and pos2 != 'P':
                    if NPlabels[i]=='':
                        NPlabels[i] = 'B'
                    NPlabels[i+1] = 'I'
        # 
        # V Faas: Kui NP-fraasi l6pus on arvu/numbrifraas ( N_Y voi N_S ), siis t6stame arvufraasi
        #         lahku, isegi kui see teatud m22ral l6huks NP-fraasi, nt 
        #               [pindala 48 ha]            ==> [pindala] [48 ha]
        #               [Järvamaal 36 283 inimest] ==> [Järvamaal] [36 283 inimest]
        #               [kasahhid 3 %]             ==> [kasahhid] [3 %]
        #               [Tallinna Lihatööstuse aktsiatest 80 protsenti] ==>
        #                      [Tallinna Lihatööstuse aktsiatest] [80 protsenti]
        #
        for i in range( len(sentence) ):
            if NPlabels[i] == 'B':
                phrase, indices = self._getPhrase( i, sentence, NPlabels )
                posTags = [ self._getPOS(tok) for tok in phrase ]
                if len(phrase)>2 and posTags[-1] in ['S','Y'] and posTags[-2]=='N' and \
                   posTags[0] not in ['N', 'O']:
                    #
                    # Lisakontroll: tegu ei tohiks olla aastarvuga, nt:
                    #    [Eesti Tervishoiuprojekt] [2015 Lisaks]
                    #    [Prantsusmaa loobumine EXPO] [2004 korraldamisest]
                    # 
                    yearCheck = re.match('.*\d\d\d\d.*', phrase[-2][TEXT])
                    #
                    # Lisakontroll: kui eelneb rohkem kui yks arv, siis tuleb 
                    #    poolitamispunkti nihutada, nt:
                    #       [Viinis 170] [000 USA dollari]
                    #       [Järvamaal 36] [283 inimest]
                    #
                    breakPoint = indices[-2]
                    j = -3
                    while posTags[j] == 'N':
                        breakPoint = indices[j]
                        j -= 1
                    if not yearCheck:
                        NPlabels[breakPoint] = 'B'

        # 
        # VI Faas: Kui NP-fraasi sobiva s6na vanem on +2 v6i rohkema s6na kaugusel s6na j2rel, 
        #          siis pole s6na veel fraasi arvatud;
        #          Arvame ta fraasi j2rgmistel juhtudel:
        #            Eelnev j2rgarv, nt:
        #                ... pühendus meenutab [teisigi] [Põhjala suurmehi] , nagu ...
        #                ... enamikus jäid [esimese] [Eesti Vabariigi aegadesse] ...
        #            Eelnev omaduss6na, nt:
        #                ... makett ühest [olulisest] [jõeäärsest tänavast] sellisena ,
        #                ... soojendades ja [suures] soojaks [köetud telgis] kuuma teed ...
        #
        for i in range(len(sentence)-1, -1, -1):
            label1  = sentence[i][SYNTAX_LABEL]
            parent1 = sentence[i][SYNTAX_HEAD]
            pos1 = self._getPOS(sentence[i])
            parentRelativeLoc = int(parent1) - int(label1)
            if pos1 in NPattribPos and NPlabels[i]=='' and parentRelativeLoc > 1 and \
               i+parentRelativeLoc < len(sentence):
                label2  = sentence[i+parentRelativeLoc][SYNTAX_LABEL]
                parent2 = sentence[i+parentRelativeLoc][SYNTAX_HEAD]
                if int(parent1) == int(label2) and NPlabels[i+parentRelativeLoc] != '':
                    #
                    #   Kogume kokku k6ik kahe s6na vahele j22vad token'id:
                    #  
                    interveningTokens   = []
                    interveningTokenIDs = []
                    j = i + 1
                    while ( j < i + parentRelativeLoc ):
                        interveningTokens.append( sentence[j] )
                        interveningTokenIDs.append( j )
                        j += 1
                    #
                    #   Eemaldame neist tokenid, mis juba kuuluvad fraasi:
                    #
                    if NPlabels[i+parentRelativeLoc] == 'I':
                        while ( len(interveningTokenIDs) > 0 ):
                            lastID = interveningTokenIDs.pop()
                            lastToken = interveningTokens.pop()
                            if NPlabels[lastID] == 'B':
                                # Kui j6udsime fraasi alguseni, siis l6petame
                                break
                    
                    #
                    #    Kontroll1: s6na ja j2rgneva s6na vahele ei tohi j22da 
                    #     punktuatsiooni ega sidendeid, kuna need j2tame alati 
                    #     fraasist v2lja;
                    #
                    punctIntervening = False
                    jaNingEgaVoi     = False
                    for interToken in interveningTokens:
                        if self._punctPos.matches( interToken ):
                            punctIntervening = True
                        if self._jaNingEgaVoi.matches( interToken ):
                            jaNingEgaVoi = True

                    #
                    #   Leiame s6na ja tema ylema vahelise k22ndeyhilduvuse;
                    #
                    caseAgreement = \
                        self._getCaseAgreement(sentence[i], sentence[i+parentRelativeLoc])

                    if pos1 == 'O' and not punctIntervening and not jaNingEgaVoi and \
                       caseAgreement != None:
                        if len(interveningTokenIDs) == 0:
                            #
                            #    VI.a.  Eelnev s6na on k22ndes yhilduv j2rgarv, nt:
                            #      ... nagu ka teised [Eesti pered] , iga ...
                            #        ... mil esimene [Tšetšeenia sõda] käis täie ...
                            #        ... ka mõnedel teistel [mineraalsetel kütetel] peale autobensiini ...
                            #        ... on pärit kolmandast [Moosese raamatust] ehk leviitide ...
                            #
                            NPlabels[i]   = 'B'
                            NPlabels[i+1] = 'I'
                        else:
                            #
                            #    VI.b.  Eelnev s6na on k22ndes yhilduv j2rgarv, ning vahele j22vad
                            #           ainult k22ndes yhilduvad s6nad, nt:
                            #        ... Teised sõjavastased [Euroopa riigid] ilmselt avaldavad ...
                            #        ... tõi ära esimesed pesuehtsad [punased värsid] . ...
                            #        ... Esimene üleriigiline [automatiseeritud haiguseregister] - vähiregister ...
                            #
                            agreements = [self._getCaseAgreement(interTok, sentence[i+parentRelativeLoc]) for interTok in interveningTokens]
                            if all(agreements):
                                NPlabels[i] = 'B'
                                j = i + 1
                                while ( j <= i + parentRelativeLoc ):
                                    NPlabels[j] = 'I'
                                    j += 1

                    if pos1 in ['A','G'] and not punctIntervening and not jaNingEgaVoi and \
                       caseAgreement != None:
                        # 
                        #   Lisakontroll 1:
                        #      Jätame algusesse lisamata kesksõnadena esinevad sõnad, kuna 
                        #      nende puhul on tõenäoliselt tegemist millegi keerukamaga (nn
                        #      lauselühendiga):
                        #        ... Pingilt sekkunud [Chris Anstey] viskas ...
                        #        ... NBA meistriks tüürinud [Phil Jackson] ...
                        #        ... kaasaegsele maailmale mittevastav [teoreetiline lähenemine] ...
                        #
                        isVerbParticle = self._verbParticle.matches(sentence[i])
                        #
                        #  Lisakontroll 2:
                        #      Kui omaduss6na ja fraasi vahele j22b ka teisi s6nu, teeme 
                        #      kindlaks, et need s6nad poleks s6naliikidest V, D, J, mis
                        #      on probleemsed, nt:
                        #       D : ...  skreipi nii [pärilik] kui ka [nakkav haigus]  ...
                        #       V : ...  2002. aasta [keskmine] purunenud [terade saak]  ...
                        #       J : ...  oleks maakondadele [sobilik] kuni [14-rühmaline loend] Eesti  ...
                        #
                        interveningProblematicPOS = False
                        if len(interveningTokenIDs) > 0:
                            iPosTags = [ a[POSTAG] for t1 in interveningTokens for a in t1[ANALYSIS] ]
                            interveningProblematicPOS = \
                              'V' in iPosTags or 'D' in iPosTags or 'J' in iPosTags or 'Z' in iPosTags
                        if not isVerbParticle and len(interveningTokenIDs) == 0:
                            #
                            #    VI.c.  Eelnev s6na on k22ndes yhilduv ja vahetult eelnev 
                            #           omaduss6na (v.a. kesks6na), nt:
                            #           ... peeti pidu karmi [vene korra] ajal ning ...
                            #           ... äravajunud , arhailisest [Suurbritannia nurgast] ...
                            #           ... , võimaldades uutel [vapratel riikidel] kahel pool ...
                            #
                            NPlabels[i]   = 'B'
                            NPlabels[i+1] = 'I'
                        elif not isVerbParticle and len(interveningTokenIDs) > 0 and \
                            not interveningProblematicPOS:
                            #
                            #    VI.d.  Eelnev s6na on k22ndes yhilduv omaduss6na (v.a. kesks6na) 
                            #           ning vahele j22b veel v2hemalt yks sobiva POS tag'iga
                            #           s6na, nt:
                            #           ... korral on [tavaline] tugev [päevane unisus] , ...
                            #           ... mõjus silmadele [vana] mustvalge pisike [ekraan] ...
                            #           ... on enesekindel [valgete] higiste [kätega intelligent] ...
                            #
                            NPlabels[i] = 'B'
                            j = i + 1
                            while ( j <= i + parentRelativeLoc ):
                                NPlabels[j] = 'I'
                                j += 1
                                
                    if pos1 in ['C'] and not punctIntervening and not jaNingEgaVoi and \
                       caseAgreement != None:
                        if i - 1 > -1  and  self._k6ige.matches( sentence[i - 1] ):
                            #
                            #    VI.e.  Eelnev s6na on k22ndes yhilduv keskv6rde omaduss6na, 
                            #           millele eelneb yliv6rde tunnus 'k6ige', nt:
                            #           ... juhib perekonda kõige noorem [täiskasvanud naine] . ...
                            #           ... Kõige suurem [akustiline erinevus] oli vokaalide ...
                            #           ... on kõige levinumad [antikolinergilised ravimid] ...
                            #
                            NPlabels[i-1] = 'B'
                            j = i
                            while ( j <= i + parentRelativeLoc ):
                                NPlabels[j] = 'I'
                                j += 1
                        elif re.match('^(pl\s.+|sg\s(ab|abl|ad|all|el|es|ill|in|kom|ter|tr))$', \
                             caseAgreement):
                            #
                            #    VI.f.  Eelnev s6na on k22ndes yhilduv keskv6rde omaduss6na, 
                            #           mis on kas mitmuses v6i yhildub semantilise k22ndega, nt:
                            #           ... olnud üks aktiivsemaid [NATO rahupartnereid] . ...
                            #           ... meestel lisandub halvemale [füüsilisele tervisele] veel ...
                            #           ... Varasemates [samalaadsetes uurimustes] on laste ...
                            #          (grammatilise ainsusek22nde puhul ei pruugi nii kindel
                            #           olla, et kuulub just nimis6nafraasi juurde: v6ib kuuluda
                            #           ka (olema) verbifraasi juurde)
                            #
                            NPlabels[i] = 'B'
                            j = i + 1
                            while ( j <= i + parentRelativeLoc ):
                                NPlabels[j] = 'I'
                                j += 1
                            
                            #ex = self.__debug_extract_NP_from_pos(sentence, NPlabels, i-1, i+parentRelativeLoc)
                            #try:
                            #    print(sentence[i][TEXT]+' | '+sentence[i+parentRelativeLoc][TEXT]+' | '+pos1+" | "+ex)
                            #except:
                            #    print(' ### Err ###')
                       


        #
        #   Viimane faas: rakendame nn j2relparandusi, proovime pahna v2lja visata ...
        #
        self.applyPostFixes( sentence, NPlabels, cutPhrases, cutMaxThreshold )
        return NPlabels


    _verbEi  = WordTemplate({ROOT:'^ei$',POSTAG:'[DV]'})  
    _verbOle = WordTemplate({ROOT:'^ole$',POSTAG:'V'})

    def applyPostFixes( self, sentence, NPlabels, cutPhrases, cutMaxThreshold ):
        '''  Fraasituvastaja j2relparandused:
            *) Tekstis6renduste eemaldamine (s6rendatud tekst ei pruugi olla 
                fraas, v6ib olla nt terve lause);
            *) Problemaatiliste kesks6nade eemaldamine fraasialgusest;
            *) Ainult arvs6nadest koosnevate fraaside eemaldamine;
            *) ...
            *) B/I m2rkide parandus;
            *) Fraaside l6ikamine sobivasse pikkusse (kui cutPhrases==True ja
               cutMaxThreshold on seadistatud);
        '''
        for i in range( len(sentence) ):
            if NPlabels[i] == 'B':
                phrase, indices = self._getPhrase( i, sentence, NPlabels )
                posTags = [ self._getPOS(tok) for tok in phrase ]
                #
                #   1) Eemaldame tekstis6rendused, mis kogemata kombel on loetud
                #      eraldi s6nadeks ja s6nade liitmise abil saadud fraasid, nt:
                #       et [õ i g e k e e l s u s r a a m a t u i s] sisaldub
                #       , [k u s v õ i m i l l a l] ma
                #
                if len(posTags) > 1 and len( set(posTags).difference(set(['Y'])) )==0:
                    # Kustutame fraasi
                    for k in indices:
                        NPlabels[k] = ''
                if len(posTags) > 1 and posTags[0] == 'A':
                    forms = [ a[FORM] for a in phrase[0][ANALYSIS] ]
                    if 'nud' in forms or 'tud' in forms or 'dud' in forms:
                        #
                        #   2) Eemaldame nud/tud fraasi algusest, kui nud/tud 
                        #      moodustavad toenaolisel liitoeldise, nt:
                        #           täpselt on [jälgitud seadust] .
                        #           Töötud on [kutsunud protestiga] liituma ka töölisi
                        #           ise ei [saanud naeru] pidama . "
                        #
                        if i - 1  >  -1 and ( \
                           self._verbEi.matches(sentence[i-1]) or \
                           self._verbOle.matches(sentence[i-1]) ):
                           NPlabels[i] = ''
                           #print(self.__debug_extract_NP_from_pos(sentence, NPlabels, i))
                if len(phrase) > 1 and set(posTags).issubset(set(['O', 'N'])):
                    #
                    #   3) Eemaldame vaid arvs6nadest koosnevad fraasid, nt:
                    #           , vaid [800 miljonit] .
                    #           põhjustel umbes [100 000.] 
                    #           kolmandat ja [kolmas neljandat] .
                    #           üleeuroopalisel konkursil [esimese kolme] hulka .
                    #           1990. aastate [teisel poolel] .
                    #           võitis küll [esimese veerandi 31] : 13 ,
                    #
                    for k in indices:
                        NPlabels[k] = ''
                if posTags.count( 'N' ) > 7:
                    #
                    #   4) Eemaldame ylipikaks veninud numbrifraasid (kuna on kahtlus,
                    #      et sellisel juhul pole tegu mitte numbrifraasiga, vaid
                    #      mingi loetelu/tabeli vms-ga), nt:
                    #         Vaip , [1 1 1 1 1 0 1 1 1 1 Vaip] [ : 2
                    #         [1 0 0 0 0 1 1 1 1 B] Ühes Eesti ettevõttes
                    #  
                    for k in range( len(indices) ):
                        ind = indices[k]
                        pos = posTags[k]
                        if pos == 'N' and ( k==0 or (k>0 and NPlabels[ind-1]=='') ):
                            NPlabels[ind] = ''
                        elif ( k > 0 and NPlabels[ind-1] == '' ):
                            NPlabels[ind] = 'B'
                        elif ( k > 0 and NPlabels[ind-1] != '' ):
                            NPlabels[ind] = 'I'

                #  Kontrollime, kas fraasis eelneb suurt2helisele s6nale 
                #    mineviku kesks6na, mis pole suurt2heline;                
                verbPartFollowedByTitle = -1
                for j in range( len(phrase) ):
                    if self._verbPastParticle.matches( phrase[j] ) and \
                       not phrase[j][TEXT].istitle() and \
                       j+1 < len(phrase) and \
                       phrase[j+1][TEXT].istitle():
                        verbPartFollowedByTitle = j
                if verbPartFollowedByTitle == 0:
                    #   
                    #  5) P2risnimele eelneva kesks6na kustutamine:
                    #     P2risnimele eelnev kesks6na on sageli probleemne, st v6ib olla:
                    #           a) seotud eelneva verbiga, nt:
                    #               ... Hiibus ei [jätnud Elviiret] kiitmata ...
                    #              ... on isa-ema kodu [vahetanud Kohila] vastu ...
                    #              ... on aastaid [olnud Valgemäe perenaine] ...
                    #           b) olla osa keerukamast nimis6nafraasist (lauselyhendist), nt:
                    #              ... revolutsiooni ellu [viinud Reagan] oli ametist lahkudes ...
                    #              ... olümpiamängude A-normi [täitnud Uusorg] ...
                    #      Seet6ttu kustutame teatud tingimustel eelneva kesks6na maha;
                    #
                    NPlabels[indices[verbPartFollowedByTitle]]   = ''
                    NPlabels[indices[verbPartFollowedByTitle]+1] = 'B'

                if posTags[0] == 'C' and i + 1 > -1 and NPlabels[i-1] == '':
                    #   
                    #  6) Puuduva 'kõige' lisamine fraasile, mille alguses on C, nt:
                    #      ... Kõige [selgemal päeval] läksin ma taas ...
                    #      ... Ka kõige [avarama ruumiihalusega eurooplane] talub Hiinas ...  
                    #      ... Kõige [nõrgema toimega] olid harilik puju ...
                    #
                    if self._k6ige.matches( sentence[i-1] ):
                        NPlabels[i-1] = 'B'
                        NPlabels[i]   = 'I'
                if posTags[0] == 'C' and len( posTags ) == 2 and posTags[1] == 'H' and \
                   NPlabels[i] == 'B':
                    #
                    #  7) Empiiriline tähelepanek - kui pärisnime ees on komparatiiv-
                    #     omadussõna, siis enamasti on tegu katkise fraasiga, nt:
                    #       ... nähtavas tulevikus [tähtsam Balkanitel] toimuv kui ...
                    #       ... oma eluasemekuludeks [varasema Tallinnas] kehtinud ...
                    #       ... 30 kraadi [paremal Jedinstvost] ( Ühtsusest ) ...
                    #     Seetõttu eemaldame fraasist C;
                    #
                    NPlabels[i]   = ''
                    NPlabels[i+1] = 'B'

        # X) Kui kogemata on sattunud m6ni iseseisev 'I' (ilma eelneva 'I' v6i 'B'-ta),
        #    muudame selle 'B'-ks
        for i in range( len(sentence) ):
            if NPlabels[i] == 'I':
                if i == 0 or (i-1>-1 and NPlabels[i-1] not in ['I','B']):
                    NPlabels[i] = 'B'

        #
        # Y) Kui on n6utud fraaside l6ikamine pikkuse j2rgi (j2tta alles vaid fraasid
        #    pikkusega N), l6ikame pikkust N yletavad fraasid juppideks nii, et alles
        #    j22vad vaid fraasi peas6naks sobivad s6nad;
        #
        if cutPhrases and cutMaxThreshold > 0:
            NPheadPos = [ 'S', 'Y', 'H' ]
            for i in range( len(sentence) ):
                if NPlabels[i] == 'B':
                    phrase, indices = self._getPhrase( i, sentence, NPlabels )
                    posTags = [ self._getPOS(tok) for tok in phrase ]
                    if len(phrase) > cutMaxThreshold:
                        for j in range(len(phrase)):
                            posTag = posTags[j]
                            if posTag in NPheadPos:
                                # J2tame alles vaid nimis6nafraasi peas6nadeks
                                # sobivad s6nad, yksikute s6nadena;
                                NPlabels[indices[j]] = 'B'
                            else:
                                # Kui s6na ei sobi peas6naks, kustutame sellelt
                                # yldse m2rgenduse;
                                NPlabels[indices[j]] = ''




    # ===========================================================
    #   Debugging stuff
    # ===========================================================
    
    def __debug_get_text_snippet(self, sentence, fromIndex, toIndex):
        minIndex = max(fromIndex, 0)
        maxIndex = min(toIndex, len(sentence)-1)
        if minIndex == maxIndex:
            return sentence[minIndex][TEXT]
        elif minIndex < maxIndex:
            return ' '.join([sentence[k][TEXT] for k in range(minIndex, maxIndex+1)])
        else:
            return ''

    def __debug_extract_NP_from_pos(self, sentence, np_labels, minpos, maxpos, context = 2):
        if 0 <= minpos and minpos <= maxpos and maxpos < len(sentence):
            text = []
            j = minpos
            while (j <= maxpos):
                if np_labels[j] == 'B':
                    text.append('['+sentence[j][TEXT])
                else:
                    text.append( sentence[j][TEXT])  
                if j+1 < len(sentence) and np_labels[j+1] in ['B', ''] and np_labels[j] in ['B', 'I']:
                    text[-1] += ']'
                elif j+1 == len(sentence) and np_labels[j] in ['B', 'I']:
                    text[-1] += ']'
                j+=1
            text = ' '.join(text)
            pre  = self.__debug_get_text_snippet(sentence, minpos-context, minpos-1)
            text = pre+' '+text
            post = self.__debug_get_text_snippet(sentence, maxpos+1, maxpos+context)
            text = text+' '+post
            return text
        return ''
