import pickle
import random
import pathlib
import os.path
import inflect
import argparse
import requests
import safygiphy
import math
import numpy
import slide_templates
from random import randint
from os import listdir
from os.path import isfile, join

from bs4 import BeautifulSoup

import nltk
from nltk.corpus import wordnet as wn
from py_thesaurus import Thesaurus
from google_images_download import google_images_download


# Slide generator class
class SlideGenerator:

    # Class function to create a function that always returns a certain weight
    def constant_weight(weight: int):
        return lambda slide_nr, total_slides: weight

    def __init__(self, generator, weight_function=constant_weight(1), name=None):
        self._generator = generator
        self._weight_function = weight_function
        self._name = name

    # Generate a slide for a given presentation using the given seed.
    def generate(self, presentation, seed):
        slide = self._generator(presentation, seed)
        # Add information about the generator to the notes
        if slide:
            slide.notes_slide.notes_text_frame.text = str(self) + " / " + seed
        return slide

    # The weight of the generator for a particular slide.
    # Determines how much chance it has being picked for a particular slide number
    def get_weight_for(self, slide_nr, total_slides):
        return self._weight_function(slide_nr, total_slides)

    def __str__(self):
        name = str(self._generator.__name__)
        if name == '<lambda>':
            name = str(self._name)
        return "SlideGenerator[" + name + "]"


# Class responsible for determining which slide generators to use in a presentation, and how the (topic) seed for
# each slide is generated
class PresentationSchema:

    def __init__(self, seed_generator, slide_generators):
        self._seed_generator = seed_generator
        self._slide_generators = slide_generators

    # Generate a presentation about a certain topic with a certain number of slides
    def generate_presentation(self, topic, num_slides):

        # Create new presentation
        presentation = slide_templates.create_new_powerpoint()
        # Create the topic-for-each-slide generator
        seed_generator = self._seed_generator(topic, num_slides)

        for slide_nr in range(num_slides):
            self._generate_slide(presentation, seed_generator, slide_nr, num_slides, set())

        return presentation

    def _generate_slide(self, presentation, seed_generator, slide_nr, num_slides, prohibited_generators=set()):

        # Generate a topic for the next slide
        seed = seed_generator.generate_seed(slide_nr)

        # Select the slide generator to generate with
        generator = self._select_generator(slide_nr, num_slides, prohibited_generators)

        print('Generating slide {} about {} using {}'.format(slide_nr + 1, seed, generator))
        slide = generator.generate(presentation, seed)

        # Try again if slide is None, and prohibit generator for generating for this topic
        if not bool(slide):
            prohibited_generators.add(generator)

            return self._generate_slide(presentation, seed_generator, slide_nr, num_slides, prohibited_generators)
            # TODO: Remove slide from presentation if there was a slide generated

        return slide

    # Select a generator for a certain slide number
    def _select_generator(self, slide_nr, total_slides, prohibited_generators):
        weighted_generators = []
        for i in range(len(self._slide_generators)):
            generator = self._slide_generators[i]
            if generator in prohibited_generators:
                continue
            weighted_generator = generator.get_weight_for(slide_nr, total_slides), generator
            weighted_generators.append(weighted_generator)
        return weighted_random(weighted_generators)


# This class generates a bunch of related words (e.g. synonyms) of a word to generate topics for a presentation
class SynonymTopicGenerator:

    def __init__(self, topic, number_of_slides):
        self._topic = topic
        self._slides_nr = number_of_slides
        synonyms = get_synonyms(topic)
        # seeds.extend(get_relations(topic))

        # Check if enough generated
        if len(synonyms) < number_of_slides:
            # If nothing: big problem!
            if len(synonyms) == 0:
                synonyms = [topic]

            # Now fill the seeds up with repeating topics
            number_of_repeats = int(math.ceil(number_of_slides / len(synonyms)))
            synonyms = numpy.tile(synonyms, number_of_repeats)

        # Take random `number_of_slides` elements
        random.shuffle(synonyms)
        self._seeds = synonyms[0: number_of_slides]

    def generate_seed(self, slide_nr):
        return self._seeds[slide_nr]


# HELPER FUNCTIONS
def _save_presentation_to_pptx(topic, prs):
    """Save the talk."""
    fp = './output/' + topic + '.pptx'
    # Create the parent folder if it doesn't exist
    pathlib.Path(os.path.dirname(fp)).mkdir(parents=True, exist_ok=True)
    prs.save(fp)
    print('Saved talk to {}'.format(fp))
    return True


def download_image(from_url, to_url):
    """Download image from url to path."""
    # Create the parent folder if it doesn't exist
    pathlib.Path(os.path.dirname(to_url)).mkdir(parents=True, exist_ok=True)

    # Download
    f = open(to_url, 'wb')
    f.write(requests.get(from_url).content)
    f.close()


def read_lines(file):
    return [line.rstrip('\n') for line in open(file)]


# From https://stackoverflow.com/questions/14992521/python-weighted-random
def weighted_random(pairs):
    if len(pairs) == 0:
        raise ValueError("Pairs can't be zero")
    total = sum(pair[0] for pair in pairs)
    r = randint(1, total)
    for (weight, value) in pairs:
        r -= weight
        if r <= 0:
            return value


# CONTENT GENERATORS
# These functions generate content, sometimes related to given arguments

def get_definitions(word):
    """Get definitions of a given topic word."""
    print('******************************************')
    # Get definition
    word_senses = wn.synsets(word)
    definitions = {}
    for ss in word_senses:
        definitions[ss.name()] = ss.definition()
    print('{} definitions for "{}"'.format(len(definitions), word))
    return definitions


def get_synonyms(word):
    """Get all synonyms for a given word."""
    print('******************************************')
    word_senses = wn.synsets(word)
    all_synonyms = []
    for ss in word_senses:
        all_synonyms.extend(
            [x.lower().replace('_', ' ') for x in ss.lemma_names()])
    all_synonyms.append(word)
    all_synonyms = list(set(all_synonyms))
    # print('{} synonyms for "{}"'.format(len(all_synonyms), word))
    return all_synonyms


def get_relations(word):
    """Get relations to given definitions."""
    rels = {}
    all_rel_forms = []
    all_perts = []
    all_ants = []

    word_senses = wn.synsets(word)
    for ss in word_senses:
        ss_name = ss.name()
        rels[ss_name] = {}
        for lem in ss.lemmas():
            lem_name = lem.name()
            rels[ss_name][lem_name] = {}
            rel_forms = [x.name() for x in lem.derivationally_related_forms()]
            rels[ss_name][lem_name]['related_forms'] = rel_forms
            all_rel_forms.extend(rel_forms)

            perts = [x.name() for x in lem.pertainyms()]
            rels[ss_name][lem_name]['pertainyms'] = perts
            all_perts.extend(perts)

            ants = [x.name() for x in lem.antonyms()]
            rels[ss_name][lem_name]['antonyms'] = ants
            all_ants.extend(ants)

    print('******************************************')
    print('{} derivationally related forms'.format(len(all_rel_forms)))
    print('******************************************')
    print('{} pertainyms'.format(len(all_perts)))
    print('******************************************')
    print('{} antonyms'.format(len(all_ants)))
    return rels


def get_images(synonyms, num_images):
    """Get images, first search locally then Google Image Search."""
    all_paths = {}
    if num_images > 0:
        for word in synonyms:
            all_paths[word] = get_google_images(word, num_images)

    return all_paths


def get_google_images(word, num_images=1):
    lp = 'downloads/' + word + '/'
    paths = _get_google_image_cached(word, num_images, lp)

    # If no local images, search on Google Image Search
    if len(paths) == 0:
        # Get related images at 16x9 aspect ratio
        response = google_images_download.googleimagesdownload()
        arguments = {
            'keywords': word,
            'limit': num_images,
            'print_urls': True,
            'exact_size': '1600,900',
        }
        # passing the arguments to the function
        paths_dict = response.download(arguments)
        for value in paths_dict.values():
            paths.extend(value)

        # printing absolute paths of the downloaded images
        print('paths of images', paths)
    return paths


def _get_google_image_cached(word, num_image, lp):
    paths = []
    try:
        local_files = [lp + f for f in listdir(lp) if isfile(join(lp,
                                                                  f))]
        paths = local_files
    except FileNotFoundError:
        paths = []

    if len(paths) > 0:
        print('{} local images on {} found'.format(len(paths), word))

    return paths


# GENERATORS
def generate_powerpoint_title(seed):
    """Returns a template title from a source list."""
    print('******************************************')
    chosen_synonym_plural = inflect.engine().plural(seed)
    synonym_templates = read_lines('data/text-templates/titles.txt')
    chosen_template = random.choice(synonym_templates)
    return chosen_template.format(chosen_synonym_plural.title())


def get_related_giphy(seed_word):
    giphy = safygiphy.Giphy()
    response = giphy.random(tag=seed_word)
    if response:
        giphy_url = response.get('data').get('images').get('original').get('url')
        gif_name = os.path.basename(os.path.dirname(giphy_url))
        image_url = 'downloads/' + seed_word + '/gifs/' + gif_name + ".gif"
        download_image(giphy_url, image_url)
        return image_url


def wikihow_action_to_action(wikihow_title):
    index_of_to = wikihow_title.find('to')
    return wikihow_title[index_of_to + 3:]


def search_wikihow(search_words):
    return requests.get(
        'https://en.wikihow.com/wikiHowTo?search='
        + search_words.replace(' ', '+'))


def get_related_wikihow_actions(seed_word):
    page = search_wikihow(seed_word)
    # Try again but with plural if nothing is found
    if not page:
        page = search_wikihow(inflect.engine().plural(seed_word))

    soup = BeautifulSoup(page.content, 'html.parser')
    actions_elements = soup.find_all('a', class_='result_link')
    actions = \
        list(
            map(wikihow_action_to_action,
                map(lambda x: x.get_text(), actions_elements)))

    return actions


def get_random_inspirobot_image(_):
    # Generate a random url to access inspirobot
    dd = str(random.randint(1, 73)).zfill(2)
    nnnn = random.randint(0, 9998)
    inspirobot_url = ('http://generated.inspirobot.me/'
                      '0{}/aXm{}xjU.jpg').format(dd, nnnn)

    # Download the image
    image_url = 'downloads/inspirobot/{}-{}.jpg'.format(dd, nnnn)
    download_image(inspirobot_url, image_url)

    return image_url


# FULL SLIDES GENERATORS:
# These are functions that create slides with certain (generated) content

def get_related_google_image(seed_word):
    # Get all image paths
    # img_paths = args.all_paths.get(word)
    img_paths = get_google_images(seed_word, 1)
    if img_paths:
        # Pick one of the images
        img_path = random.choice(img_paths)
        return img_path


def generate_wikihow_bold_bold_statement(seed):
    related_actions = get_related_wikihow_actions(seed)
    if related_actions:
        action = random.choice(related_actions)
        bold_statement_templates = read_lines('data/text-templates/bold-statements.txt')

        chosen_template = random.choice(bold_statement_templates)
        template_values = {'action': action.title(),
                           # TODO: Make a scraper that scrapes a step related to this action on wikihow.
                           # TODO: Fix action_infinitive
                           'action_infinitive': action.title(),
                           'step': 'Do Whatever You Like',
                           'topic': seed,
                           # TODO: Use datamuse or some other mechanism of finding a related location
                           'location': 'Here'}
        life_lesson = chosen_template.format(**template_values)

        # Turn into image slide
        return life_lesson


# COMPILATION

def compile_talk_to_raw_data(arguments):
    """Save the raw data that has been harvested."""
    with open('output/' + arguments.topic.replace(' ', '_') + '.pkl', 'wb') as fh:
        pickle.dump(arguments, fh, protocol=pickle.HIGHEST_PROTOCOL)
        print('Pickle saved to output/' + arguments.topic.replace(' ', '_') + '.pkl')


# MAIN

def main(arguments):
    """Make a talk with the given topic."""
    # Print status details
    print('******************************************')
    print("Making {} slide talk on: {}".format(arguments.num_slides, arguments.topic))

    # Parse topic string to parts-of-speech
    # text = nltk.word_tokenize(args.topic)
    # print('******************************************')
    # print('tokenized text: ', text)
    # print('pos tag text: ', nltk.pos_tag(text))

    # Parse the actual topic subject from the parts-of-speech
    # topic_string = args.topic

    # Get definitions
    # args.definitions = get_definitions(topic_string)
    # Get relations
    # args.relations = get_relations(topic_string)
    # Get synonyms
    # args.synonyms = get_synonyms(topic_string)
    # Get related actions
    # args.actions = get_related_wikihow_actions(topic_string)
    # Get a title
    # args.title = generate_powerpoint_title(args.synonyms)
    # For each synonym download num_images
    # args.all_paths = get_images(args.synonyms, args.num_images)

    # Compile and save the presentation to data
    compile_talk_to_raw_data(arguments)

    # Compile and save the presentation to PPTX
    # compile_talk_to_pptx(args)
    presentation = presentation_schema.generate_presentation(arguments.topic, arguments.num_slides)

    # Save presentation
    _save_presentation_to_pptx(arguments.topic, presentation)


def none_generator(_):
    return None


def identity_generator(input):
    return input


# This object holds all the information about how to generate the presentation
presentation_schema = PresentationSchema(
    # Topic per slide generator
    lambda topic, num_slides: SynonymTopicGenerator(topic, num_slides),

    # Slide generators
    [SlideGenerator(slide_templates.generate_title_slide(generate_powerpoint_title),
                    # Make title slides only happen as first slide
                    # TODO probably better to create cleaner way of forcing positional slides
                    weight_function=lambda slide_nr, total_slides:
                    100000 if slide_nr == 0 else 0,
                    name="Title slide"),
     # TODO : Make the generators below use normal images
     SlideGenerator(slide_templates.generate_full_image_slide(identity_generator, get_related_giphy), name="Giphy"),
     SlideGenerator(slide_templates.generate_full_image_slide(none_generator, get_random_inspirobot_image),
                    name="Inspirobot"),
     SlideGenerator(slide_templates.generate_text_slide(generate_wikihow_bold_bold_statement),
                    name="Wikihow Bold Statmenet"),
     SlideGenerator(slide_templates.generate_full_image_slide(identity_generator, get_related_google_image),
                    name="Google Images")
     ]
)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Process some integers.')
    parser.add_argument('--topic', help="Topic of presentation.",
                        default='bagels', type=str)
    parser.add_argument('--num_images', help="Number of images per synonym.",
                        default=1, type=int)
    parser.add_argument('--num_slides', help="Number of slides to create.",
                        default=3, type=int)
    args = parser.parse_args()
    main(args)
